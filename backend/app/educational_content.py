# backend/app/educational_content.py
# Educational content generation: flashcards, quiz, assessment
import os
import json
from typing import Dict, List, Tuple, Union, Optional
import xlsxwriter
from .models import GenerateContentRequest, FlashcardConfig, QuizConfig, AssessmentConfig
from . import deps
from .content_utils import (
    content_client, get_rag_context_for_internal_mode, 
    validate_rag_context_for_internal_mode, extract_openai_response
)


async def generate_flashcard_content(request: GenerateContentRequest, config: FlashcardConfig) -> str:
    """Generate flashcard content in a clean table format."""
    print(f"[DEBUG] generate_flashcard_content called with config: {config}")
    print(f"[DEBUG] config type: {type(config)}")
    print(f"[DEBUG] config.num_cards: {config.num_cards}")
    
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    system_prompt = f"""You are an educational content generator. Create flashcards in a clean table format with the following specifications:
- Create exactly {config.num_cards} flashcards based on the topic
- Each flashcard should have a KEY (term/concept) and Description (explanation)
- Format as a clean table with two columns: KEY and Description
- Difficulty: {config.difficulty}
- User role: {request.role}"""
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate flashcards. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create flashcards based on the information in the context above
- Use specific terms and concepts found in the documents
- Ensure accuracy to the source material
- If the context doesn't cover the topic fully, create flashcards based on what is available"""
    else:
        system_prompt += """

Format the output as a clean table like this:
| KEY | Description |
|-----|-------------|
| Term 1 | Clear explanation of term 1 |
| Term 2 | Clear explanation of term 2 |

Make sure the table is well-structured and easy to read."""
    
    user_prompt = f"""Create flashcards based on: {request.prompt}
Number of cards: {config.num_cards}
Difficulty: {config.difficulty}

Generate exactly {config.num_cards} flashcards in a clean table format with KEY and Description columns."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return extract_openai_response(response)


def _parse_markdown_table_to_rows(table_text: str) -> List[Tuple[str, str]]:
    """Parse a markdown table with two columns (KEY, Description) into rows."""
    rows: List[Tuple[str, str]] = []
    lines = [ln.strip() for ln in table_text.splitlines() if ln.strip()]
    for ln in lines:
        if '|' not in ln:
            continue
        # Skip markdown separator rows like: |-----|------|
        if set(ln.replace('|', '').replace(' ', '').replace(':', '')) <= {'-',}:
            continue
        parts = [p.strip() for p in ln.split('|')]
        # Typical markdown rows start and end with '|', remove empties created by split
        parts = [p for p in parts if p != '']
        if len(parts) < 2:
            continue
        # Skip a possible header row if it looks like headers
        if parts[0].lower() in ("key", "term") and parts[1].lower().startswith("description"):
            continue
        key_col, desc_col = parts[0], parts[1]
        if key_col and desc_col:
            rows.append((key_col, desc_col))
    return rows


def _write_flashcards_csv_xlsx(storage_path: str, rows: List[Tuple[str, str]], base_filename: str = "flashcards") -> str:
    """Write flashcards to XLSX file WITHOUT header row. Returns xlsx_path."""
    xlsx_path = os.path.join(storage_path, f"{base_filename}.xlsx")

    # XLSX - NO HEADER ROW
    workbook = xlsxwriter.Workbook(xlsx_path)
    worksheet = workbook.add_worksheet("Flashcards")
    
    # Write data directly without header (start from row 0)
    for idx, (k, d) in enumerate(rows):
        worksheet.write(idx, 0, k)
        worksheet.write(idx, 1, d)
    
    # Make columns a bit wider
    worksheet.set_column(0, 0, 28)
    worksheet.set_column(1, 1, 80)
    workbook.close()

    return xlsx_path


async def generate_quiz_content(request: GenerateContentRequest, config: QuizConfig) -> str:
    """Generate quiz content in a structured table format."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Determine if we need to handle true/false questions
    has_true_false = "true_false" in config.question_types
    has_multiple_choice = "multiple_choice" in config.question_types
    is_mixed = has_true_false and has_multiple_choice
    
    if has_true_false and not has_multiple_choice:
        # Only true/false questions - 2 options
        system_prompt = f"""You are an educational quiz generator. Create a quiz in a structured table format with the following specifications:
- Number of questions: {config.num_questions}
- Difficulty: {config.difficulty}
- Question types: True/False only
- User role: {request.role}

Format the output as a structured table with these columns:
| S.No. | QUESTION | CORRECT ANSWER | ANSWER DESC | ANSWER 1 | ANSWER 2 |

Where:
- S.No.: Serial number (1, 2, 3, etc.)
- QUESTION: The quiz question (must be a statement that can be answered as True or False)
- CORRECT ANSWER: The number (1 or 2) indicating which answer is correct (1 = True, 2 = False)
- ANSWER DESC: Brief explanation of why the correct answer is right
- ANSWER 1: "True"
- ANSWER 2: "False"

Make sure each question has exactly 2 answer choices (True and False) and the correct answer number corresponds to one of them."""
    else:
        # Multiple choice or mixed - 4 options
        question_type_desc = "Mixed (Multiple Choice and True/False)" if is_mixed else "Multiple Choice"
        system_prompt = f"""You are an educational quiz generator. Create a quiz in a structured table format with the following specifications:
- Number of questions: {config.num_questions}
- Difficulty: {config.difficulty}
- Question types: {question_type_desc}
- User role: {request.role}

Format the output as a structured table with these columns:
| S.No. | QUESTION | CORRECT ANSWER | ANSWER DESC | ANSWER 1 | ANSWER 2 | ANSWER 3 | ANSWER 4 |

Where:
- S.No.: Serial number (1, 2, 3, etc.)
- QUESTION: The quiz question
- CORRECT ANSWER: The number (1, 2, 3, or 4) indicating which answer is correct
- ANSWER DESC: Brief explanation of why the correct answer is right
- ANSWER 1-4: Four multiple choice options

{"For True/False questions in mixed mode, use ANSWER 1 = 'True' and ANSWER 2 = 'False', and ANSWER 3 = 'NA', ANSWER 4 = 'NA'." if is_mixed else ""}
Make sure each question has exactly 4 answer choices and the correct answer number corresponds to one of them."""
    
    user_prompt = f"""Create a quiz based on: {request.prompt}
Number of questions: {config.num_questions}
Difficulty: {config.difficulty}
Question types: {', '.join(config.question_types)}

Generate the quiz in the exact table format specified above."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return extract_openai_response(response)


async def generate_quiz_table(request: GenerateContentRequest, config: QuizConfig) -> List[Dict[str, Union[str, int]]]:
    """Generate quiz rows suitable for CSV/XLSX export with answer description."""
    if not content_client:
        raise Exception("OpenAI client not configured")

    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context

    # Determine question type handling
    has_true_false = "true_false" in config.question_types
    has_multiple_choice = "multiple_choice" in config.question_types
    is_mixed = has_true_false and has_multiple_choice
    is_only_true_false = has_true_false and not has_multiple_choice

    # Set keys based on question type
    if is_only_true_false:
        # Only true/false - no answer_3 and answer_4
        keys = [
            "s_no","question","correct_answer","answer_desc","answer_1","answer_2"
        ]
    else:
        # Multiple choice or mixed - include all 4 answers
        keys = [
            "s_no","question","correct_answer","answer_desc","answer_1","answer_2","answer_3","answer_4"
        ]

    if is_only_true_false:
        # Only true/false questions - 2 options (no answer_3 or answer_4)
        system_prompt = (
            "You generate quiz rows for CSV/XLSX export. Return ONLY JSON array (no markdown) "
            "with objects using EXACT keys: " + ",".join(keys) + ". "
            "'s_no' starts at 1 and increments. 'correct_answer' is 1 or 2 (1 = True, 2 = False). "
            "'answer_desc' is a brief explanation of why the correct answer is right (20-50 words). "
            f"Create exactly {config.num_questions} rows. Difficulty: {config.difficulty}. "
            "All questions must be True/False format. "
            "For each question: answer_1 must be 'True', answer_2 must be 'False'. "
            "Do NOT include answer_3 or answer_4 keys in the JSON objects. "
            "Generate realistic, educational content."
        )
        user_prompt = (
            f"Create quiz rows for: {request.prompt}. "
            f"Keep questions concise and unambiguous. "
            f"For each row, provide: s_no, question (must be a statement that can be answered True/False), "
            f"correct_answer (1 for True, 2 for False), answer_desc (why the answer is correct), "
            f"answer_1 = 'True', answer_2 = 'False'. "
            f"Do NOT include answer_3 or answer_4. "
            f"Make it realistic and educational."
        )
    elif is_mixed:
        # Mixed: multiple choice and true/false
        system_prompt = (
            "You generate quiz rows for CSV/XLSX export. Return ONLY JSON array (no markdown) "
            "with objects using EXACT keys: " + ",".join(keys) + ". "
            "'s_no' starts at 1 and increments. 'correct_answer' is 1-4 for multiple choice, 1-2 for true/false. "
            "'answer_desc' is a brief explanation of why the correct answer is right (20-50 words). "
            f"Create exactly {config.num_questions} rows. Difficulty: {config.difficulty}. "
            "Mix multiple choice questions (with 4 options) and true/false questions (answer_1='True', answer_2='False', answer_3='NA', answer_4='NA'). "
            "Generate realistic, educational content."
        )
        user_prompt = (
            f"Create quiz rows for: {request.prompt}. "
            f"Keep questions concise and unambiguous. "
            f"Mix multiple choice questions (4 answer options) and true/false questions (answer_1='True', answer_2='False', answer_3='NA', answer_4='NA'). "
            f"For each row, provide: s_no, question, correct_answer (1-4 for multiple choice, 1-2 for true/false), "
            f"answer_desc (why the answer is correct), and appropriate answer choices. "
            f"Make it realistic and educational."
        )
    else:
        # Only multiple choice - 4 options
        system_prompt = (
            "You generate quiz rows for CSV/XLSX export. Return ONLY JSON array (no markdown) "
            "with objects using EXACT keys: " + ",".join(keys) + ". "
            "'s_no' starts at 1 and increments. 'correct_answer' is 1-4. "
            "'answer_desc' is a brief explanation of why the correct answer is right (20-50 words). "
            f"Create exactly {config.num_questions} rows. Difficulty: {config.difficulty}. "
            "All questions must be multiple choice with 4 options. "
            "Generate realistic, educational content."
        )
        user_prompt = (
            f"Create quiz rows for: {request.prompt}. "
            f"Keep questions concise and unambiguous. "
            f"For each row, provide: s_no, question, correct_answer (1-4), "
            f"answer_desc (why the answer is correct), and 4 answer choices. "
            f"Make it realistic and educational."
        )
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate quiz questions. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create quiz questions based on the information in the context above
- Ensure questions and answers are factually accurate to the source material
- Use specific details from the documents
- If the context doesn't cover the topic fully, create questions based on what is available"""

    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    txt = extract_openai_response(response).strip()
    try:
        data = json.loads(txt)
        if not isinstance(data, list):
            raise ValueError("expected list")
    except Exception:
        data = []

    rows: List[Dict[str, Union[str, int]]] = []
    for row in data:
        norm: Dict[str, Union[str, int]] = {}
        # Only include keys that are in the expected keys list
        for k in keys:
            value = row.get(k, "")
            if k == "s_no":
                # Keep as integer
                try:
                    norm[k] = int(value) if value else 0
                except (ValueError, TypeError):
                    norm[k] = 0
            elif k == "correct_answer":
                # Keep as integer
                try:
                    norm[k] = int(value) if value else 0
                except (ValueError, TypeError):
                    norm[k] = 0
            else:
                # Convert to string
                norm[k] = str(value) if value else ""
        rows.append(norm)
    
    # Post-process: For mixed mode, fill empty answer_3 and answer_4 with "NA" for true/false questions
    if is_mixed:
        for row in rows:
            answer_1 = str(row.get("answer_1", "")).strip()
            answer_2 = str(row.get("answer_2", "")).strip()
            answer_3 = str(row.get("answer_3", "")).strip()
            answer_4 = str(row.get("answer_4", "")).strip()
            
            # Detect true/false question: answer_1 is "True" and answer_2 is "False"
            is_true_false = (answer_1.lower() == "true" and answer_2.lower() == "false")
            
            if is_true_false:
                # Fill empty answer_3 and answer_4 with "NA"
                if not answer_3 or answer_3 == "":
                    row["answer_3"] = "NA"
                if not answer_4 or answer_4 == "":
                    row["answer_4"] = "NA"
    
    return rows


def _write_quiz_csv_xlsx(storage_path: str, rows: List[Dict[str, Union[str, int]]], base_filename: str = "quiz", quiz_config: Optional[QuizConfig] = None) -> str:
    """Write quiz rows to XLSX with the specified headers order including ANSWER DESC."""
    # Determine if we should include ANSWER 3 and ANSWER 4 columns
    is_only_true_false = False
    if quiz_config:
        has_true_false = "true_false" in quiz_config.question_types
        has_multiple_choice = "multiple_choice" in quiz_config.question_types
        is_only_true_false = has_true_false and not has_multiple_choice
    
    if is_only_true_false:
        # True/false only - exclude ANSWER 3 and ANSWER 4
        headers = [
            "S.No.", "QUESTION", "CORRECT ANSWER", "ANSWER DESC",
            "ANSWER 1", "ANSWER 2"
        ]
        key_map = {
            "S.No.": "s_no",
            "QUESTION": "question",
            "CORRECT ANSWER": "correct_answer",
            "ANSWER DESC": "answer_desc",
            "ANSWER 1": "answer_1",
            "ANSWER 2": "answer_2",
        }
    else:
        # Multiple choice or mixed - include all columns
        headers = [
            "S.No.", "QUESTION", "CORRECT ANSWER", "ANSWER DESC",
            "ANSWER 1", "ANSWER 2", "ANSWER 3", "ANSWER 4"
        ]
        key_map = {
            "S.No.": "s_no",
            "QUESTION": "question",
            "CORRECT ANSWER": "correct_answer",
            "ANSWER DESC": "answer_desc",
            "ANSWER 1": "answer_1",
            "ANSWER 2": "answer_2",
            "ANSWER 3": "answer_3",
            "ANSWER 4": "answer_4",
        }

    xlsx_path = os.path.join(storage_path, f"{base_filename}.xlsx")

    # XLSX
    workbook = xlsxwriter.Workbook(xlsx_path)
    ws = workbook.add_worksheet("Quiz")
    header_fmt = workbook.add_format({"bold": True})
    for col, h in enumerate(headers):
        ws.write(0, col, h, header_fmt)
    for row_idx, r in enumerate(rows, start=1):
        for col, h in enumerate(headers):
            key = key_map[h]
            value = r.get(key, "")
            # Use write_number for S.No. (column 0) and CORRECT ANSWER (column 2)
            if h == "S.No." or h == "CORRECT ANSWER":
                try:
                    num_value = int(value) if value else 0
                    ws.write_number(row_idx, col, num_value)
                except (ValueError, TypeError):
                    ws.write_number(row_idx, col, 0)
            else:
                ws.write(row_idx, col, str(value) if value else "")
    ws.set_row(0, 18)
    ws.set_column(0, len(headers)-1, 22)
    workbook.close()

    return xlsx_path


async def generate_assessment_content(request: GenerateContentRequest, config: AssessmentConfig) -> str:
    """Generate assessment content."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Generate the assessment content
    system_prompt = f"""You are an educational assessment generator. Create an assessment with the following specifications:
- Duration: {config.duration_minutes} minutes
- Difficulty: {config.difficulty}
- Question types: {', '.join(config.question_types)}
- Passing score: {config.passing_score}%
- User role: {request.role}
- Make it comprehensive and aligned with learning objectives"""
    
    user_prompt = f"""Create an assessment based on: {request.prompt}
Duration: {config.duration_minutes} minutes
Difficulty: {config.difficulty}
Question types: {', '.join(config.question_types)}
Passing score: {config.passing_score}%
Make it comprehensive and aligned with learning objectives."""
    
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    return extract_openai_response(response)


async def generate_assessment_table(request: GenerateContentRequest, config: AssessmentConfig) -> List[Dict[str, str]]:
    """Generate assessment in exact template format."""
    if not content_client:
        raise Exception("OpenAI client not configured")
    
    # Get RAG context for internal mode
    rag_result = get_rag_context_for_internal_mode(request, top_k=5)
    validate_rag_context_for_internal_mode(rag_result, request)  # Validate context relevance
    rag_context = rag_result.context
    
    columns = [
        "question", "type", "answer_description", "levels", "total_options",
        "choice_answer_one", "choice_answer_two", "choice_answer_three", 
        "choice_answer_four", "correct_answers", "tag1", "tag2"
    ]
    system_prompt = (
        "You generate assessment rows for CSV/XLSX export. "
        "Return ONLY valid JSON array (no markdown) with EXACTLY these keys: " + ",".join(columns) + ". "
        
        "RULES:\n"
        "1. 'question': Question text (can include #{IMG}, #{VID}, #{FILL})\n"
        "2. 'type': 'Choice', 'FillUp', or 'Match'\n"
        "3. 'answer_description': Brief explanation\n"
        "4. 'levels': 'Easy', 'Medium', or 'Difficult'\n"
        "5. 'total_options': Number of options - ALWAYS set to 4 for ALL question types\n"
        "   - For 'Choice': Always set to 4 (exactly 4 multiple choice options)\n"
        "   - For 'FillUp': Always set to 4 (exactly 4 answer options)\n"
        "   - For 'Match': Always set to 4 (exactly 4 matching pairs)\n"
        "6. 'choice_answer_one' to 'choice_answer_four': The answer options (exactly 4 options)\n"
        "   - For 'Choice': Provide exactly 4 multiple choice options\n"
        "   - For 'FillUp': Provide exactly 4 answer options (one for each blank)\n"
        "   - For 'Match': Provide the matching pairs\n"
        "7. 'correct_answers': '1' or '1,2' for Choice; answer text for FillUp; 'a=1,b=2,c=3' for Match\n"
        "8. 'tag1', 'tag2': Tags\n\n"
        
        "CRITICAL: For ALL question types (Choice, FillUp, Match), 'total_options' MUST be 4, and you MUST provide exactly 4 options in choice_answer_one through choice_answer_four.\n\n"
        
        f"Create exactly 4 rows. Difficulty: {config.difficulty}."
    )
    
    if rag_context:
        system_prompt += f"""

IMPORTANT: You are in INTERNAL MODE. Use the provided context from uploaded documents below to create accurate assessment questions. Base your content ONLY on the information provided in the context blocks.

CONTEXT FROM UPLOADED DOCUMENTS:
{rag_context}

Instructions:
- Create assessment questions based on the information in the context above
- Ensure questions and answers are factually accurate to the source material
- Use specific details from the documents
- If the context doesn't cover the topic fully, create questions based on what is available"""
    
    user_prompt = (
        f"Create 4 assessment rows for: {request.prompt}\n"
        f"Subject: {request.subjectName or ''}\n"
        f"Topic: {request.topicName or ''}\n"
        f"Duration: {config.duration_minutes} minutes\n"
        f"Difficulty: {config.difficulty}\n"
    )
    response = content_client.chat.completions.create(
        model=deps.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )
    txt = extract_openai_response(response).strip()
    try:
        data = json.loads(txt)
        if not isinstance(data, list):
            raise ValueError("expected list")
    except Exception as e:
        print(f"[ERROR] Failed to parse assessment JSON: {e}")
        data = []
    
    norm_rows: List[Dict[str, str]] = []
    for row in data:
        norm = {}
        for col in columns:
            value = row.get(col, "")
            norm[col] = str(value) if value else ""
        
        # Ensure ALL question types have exactly 4 total_options
        question_type = norm.get("type", "").strip().lower()
        if question_type in ["choice", "fillup", "match"]:
            norm["total_options"] = "4"
            # Ensure all 4 choice answers exist (even if empty)
            if "choice_answer_one" not in norm:
                norm["choice_answer_one"] = ""
            if "choice_answer_two" not in norm:
                norm["choice_answer_two"] = ""
            if "choice_answer_three" not in norm:
                norm["choice_answer_three"] = ""
            if "choice_answer_four" not in norm:
                norm["choice_answer_four"] = ""
        
        norm_rows.append(norm)
    
    return norm_rows


def _write_assessment_csv_xlsx(storage_path: str, rows: List[Dict[str, str]], subject_name: str = "", topic_name: str = "", base_filename: str = "assessment") -> str:
    """Write assessment rows in exact template format to XLSX."""
    
    xlsx_path = os.path.join(storage_path, f"{base_filename}.xlsx")

    # XLSX Format
    workbook = xlsxwriter.Workbook(xlsx_path)
    ws = workbook.add_worksheet("Sheet1")
    
    # Formats
    subject_fmt = workbook.add_format({
        "bold": True,
        "font_size": 12,
        "bg_color": "#FFFFFF"
    })
    
    label_fmt = workbook.add_format({
        "bold": True,
        "bg_color": "#E7E6E6",
        "border": 1,
        "align": "center",
        "valign": "vcenter"
    })
    
    data_fmt = workbook.add_format({
        "border": 1,
        "align": "left",
        "valign": "top",
        "text_wrap": True
    })
    
    # Row 1: Subject header (12 columns total: question + 11 others)
    ws.write(0, 0, subject_name, subject_fmt)
    for col in range(1, 12):
        ws.write(0, col, '', subject_fmt)
    
    # Row 2: Column labels - all 12 columns
    ws.write(1, 0, topic_name, label_fmt)
    labels = [
        "type", 
        "answer description", 
        "levels", 
        "total options",
        "choice answer one",
        "choice answer two", 
        "choice answer three",
        "choice answer four",
        "correct answers",
        "tag1",
        "tag2"
    ]
    for col, label in enumerate(labels, start=1):
        ws.write(1, col, label, label_fmt)
    
    # Rows 3+: Data
    for row_idx, r in enumerate(rows, start=2):
        # Only 4 choice answers (one through four)
        data_row = [
            r.get("question", ""),
            r.get("type", ""),
            r.get("answer_description", ""),
            r.get("levels", ""),
            r.get("total_options", ""),
            r.get("choice_answer_one", ""),
            r.get("choice_answer_two", ""),
            r.get("choice_answer_three", ""),
            r.get("choice_answer_four", ""),
            r.get("correct_answers", ""),
            r.get("tag1", ""),
            r.get("tag2", ""),
        ]
        for col, value in enumerate(data_row):
            ws.write(row_idx, col, value, data_fmt)
    
    # Set column widths (12 columns total: 0-11)
    ws.set_column(0, 0, 20)  # question
    ws.set_column(1, 1, 12)  # type
    ws.set_column(2, 2, 20)  # answer description
    ws.set_column(3, 3, 10)  # levels
    ws.set_column(4, 4, 12)  # total options
    ws.set_column(5, 8, 15)  # choice_answer_one through four (columns 5-8)
    ws.set_column(9, 9, 12)  # correct answers
    ws.set_column(10, 11, 15)  # tag1, tag2
    
    # Set row heights
    ws.set_row(0, 18)
    ws.set_row(1, 20)
    for i in range(2, len(rows) + 2):
        ws.set_row(i, 35)
    
    workbook.close()

    return xlsx_path

