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
            "s_no", "question", "correct_answer", "answer_desc", "answer_1", "answer_2"
        ]
    else:
        # Multiple choice or mixed - include all 4 answers
        keys = [
            "s_no", "question", "correct_answer", "answer_desc", "answer_1", "answer_2", "answer_3", "answer_4"
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
- Number of questions: {config.num_questions}
- Difficulty: {config.difficulty}
- Question types: {', '.join(config.question_types)}
- Passing score: {config.passing_score}%
- User role: {request.role}
- Make it comprehensive and aligned with learning objectives"""
    
    user_prompt = f"""Create an assessment based on: {request.prompt}
Number of questions: {config.num_questions}
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
    
    # Determine question type handling
    has_multiple_choice = "multiple_choice" in config.question_types
    has_true_false = "true_false" in config.question_types
    has_essay = "essay" in config.question_types
    is_mixed = len(config.question_types) > 1
    
    columns = [
        "question", "type", "answer_description", "levels", "total_options",
        "choice_answer_one", "choice_answer_two", "choice_answer_three", 
        "choice_answer_four", "correct_answers", "tag1", "tag2"
    ]
    
    # Build type instructions based on question types
    type_instructions = []
    if has_multiple_choice:
        type_instructions.append("'Choice' (multiple choice with 4 options)")
    if has_true_false:
        type_instructions.append("'TrueFalse' (true/false with 2 options: True/False)")
    if has_essay:
        type_instructions.append("'Essay' (essay questions - leave choice_answer fields empty or use for sample answers)")
    
    type_desc = ", ".join(type_instructions) if type_instructions else "'Choice'"
    
    system_prompt = (
        "You generate assessment rows for CSV/XLSX export. "
        "Return ONLY valid JSON array (no markdown) with EXACTLY these keys: " + ",".join(columns) + ". "
        
        "RULES:\n"
        "1. 'question': Question text (can include #{IMG}, #{VID}, #{FILL})\n"
        f"2. 'type': One of {type_desc}\n"
        "3. 'answer_description': Brief explanation or sample answer\n"
        "4. 'levels': 'Easy', 'Medium', or 'Difficult'\n"
        "5. 'total_options': Number of options\n"
        "   - For 'Choice': Always set to 4 (exactly 4 multiple choice options)\n"
        "   - For 'TrueFalse': Always set to 2 (True and False)\n"
        "   - For 'Essay': Set to 0 or leave empty (no multiple choice options)\n"
        "6. 'choice_answer_one' to 'choice_answer_four': The answer options\n"
        "   - For 'Choice': Provide exactly 4 multiple choice options\n"
        "   - For 'TrueFalse': Provide 'True' in choice_answer_one, 'False' in choice_answer_two, leave others empty\n"
        "   - For 'Essay': Leave empty or provide sample answer points\n"
        "7. 'correct_answers': '1' or '1,2' for Choice; '1' or '2' for TrueFalse; leave empty for Essay\n"
        "8. 'tag1', 'tag2': Tags\n\n"
        
        f"Create exactly {config.num_questions} rows. Difficulty: {config.difficulty}.\n"
    )
    
    if is_mixed:
        system_prompt += (
            f"IMPORTANT: Mix the question types ({', '.join(config.question_types)}). "
            f"Distribute them evenly across the {config.num_questions} questions.\n\n"
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
        f"Create {config.num_questions} assessment rows for: {request.prompt}\n"
        f"Subject: {request.subjectName or ''}\n"
        f"Topic: {request.topicName or ''}\n"
        f"Number of questions: {config.num_questions}\n"
        f"Question types: {', '.join(config.question_types)}\n"
        f"Difficulty: {config.difficulty}\n"
        f"Passing score: {config.passing_score}%\n"
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
        
        # Ensure question types have correct total_options
        question_type = norm.get("type", "").strip()
        question_type_lower = question_type.lower()
        
        if question_type_lower in ["choice", "fillup", "match"]:
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
        elif question_type_lower in ["truefalse", "true_false"]:
            norm["total_options"] = "2"
            # Ensure True/False options
            if "choice_answer_one" not in norm or not norm["choice_answer_one"]:
                norm["choice_answer_one"] = "True"
            if "choice_answer_two" not in norm or not norm["choice_answer_two"]:
                norm["choice_answer_two"] = "False"
            if "choice_answer_three" not in norm:
                norm["choice_answer_three"] = ""
            if "choice_answer_four" not in norm:
                norm["choice_answer_four"] = ""
        elif question_type_lower == "essay":
            norm["total_options"] = "0"
            # Essay questions don't need choice answers, but ensure fields exist
            if "choice_answer_one" not in norm:
                norm["choice_answer_one"] = ""
            if "choice_answer_two" not in norm:
                norm["choice_answer_two"] = ""
            if "choice_answer_three" not in norm:
                norm["choice_answer_three"] = ""
            if "choice_answer_four" not in norm:
                norm["choice_answer_four"] = ""
        
        norm_rows.append(norm)
    
    # Post-process for mixed mode: Fill empty cells with NA for true/false and essay
    has_multiple_choice = "multiple_choice" in config.question_types
    has_true_false = "true_false" in config.question_types
    has_essay = "essay" in config.question_types
    is_mixed = len(config.question_types) > 1
    
    if is_mixed:
        for row in norm_rows:
            qtype = row.get("type", "").strip().lower()
            
            if qtype in ["truefalse", "true_false"]:
                # Fill choice_answer_three and choice_answer_four with NA
                if not row.get("choice_answer_three") or row.get("choice_answer_three") == "":
                    row["choice_answer_three"] = "NA"
                if not row.get("choice_answer_four") or row.get("choice_answer_four") == "":
                    row["choice_answer_four"] = "NA"
            
            elif qtype == "essay":
                # Fill total_options, choice answers, and correct_answers with NA
                if not row.get("total_options") or row.get("total_options") == "":
                    row["total_options"] = "NA"
                if not row.get("choice_answer_one") or row.get("choice_answer_one") == "":
                    row["choice_answer_one"] = "NA"
                if not row.get("choice_answer_two") or row.get("choice_answer_two") == "":
                    row["choice_answer_two"] = "NA"
                if not row.get("choice_answer_three") or row.get("choice_answer_three") == "":
                    row["choice_answer_three"] = "NA"
                if not row.get("choice_answer_four") or row.get("choice_answer_four") == "":
                    row["choice_answer_four"] = "NA"
                if not row.get("correct_answers") or row.get("correct_answers") == "":
                    row["correct_answers"] = "NA"
    
    return norm_rows


def _write_assessment_csv_xlsx(storage_path: str, rows: List[Dict[str, str]], subject_name: str = "", topic_name: str = "", base_filename: str = "assessment", assessment_config: Optional[AssessmentConfig] = None) -> str:
    """Write assessment rows in exact template format to XLSX."""
    
    xlsx_path = os.path.join(storage_path, f"{base_filename}.xlsx")

    # Determine question types from config or rows
    has_multiple_choice = False
    has_true_false = False
    has_essay = False
    is_mixed = False
    
    if assessment_config:
        has_multiple_choice = "multiple_choice" in assessment_config.question_types
        has_true_false = "true_false" in assessment_config.question_types
        has_essay = "essay" in assessment_config.question_types
        is_mixed = len(assessment_config.question_types) > 1
    else:
        # Infer from rows
        question_types_in_rows = set()
        for row in rows:
            qtype = row.get("type", "").strip().lower()
            if qtype in ["choice", "fillup", "match"]:
                question_types_in_rows.add("multiple_choice")
            elif qtype in ["truefalse", "true_false"]:
                question_types_in_rows.add("true_false")
            elif qtype == "essay":
                question_types_in_rows.add("essay")
        has_multiple_choice = "multiple_choice" in question_types_in_rows
        has_true_false = "true_false" in question_types_in_rows
        has_essay = "essay" in question_types_in_rows
        is_mixed = len(question_types_in_rows) > 1
    
    # Determine which columns to include
    is_essay_only = has_essay and not has_multiple_choice and not has_true_false
    is_true_false_only = has_true_false and not has_multiple_choice and not has_essay
    
    # Base columns (always included)
    base_columns = ["question", "type", "answer_description", "levels"]
    base_labels = ["type", "answer description", "levels"]
    
    # Optional columns
    include_total_options = not is_essay_only
    include_choice_one = not is_essay_only
    include_choice_two = not is_essay_only
    include_choice_three = not is_essay_only and not is_true_false_only
    include_choice_four = not is_essay_only and not is_true_false_only
    include_correct_answers = not is_essay_only
    include_tags = True  # Always include tags
    
    # Build column list and labels
    columns = base_columns.copy()
    labels = base_labels.copy()
    column_map = {
        "question": 0,
        "type": 1,
        "answer_description": 2,
        "levels": 3
    }
    col_idx = 4
    
    if include_total_options:
        columns.append("total_options")
        labels.append("total options")
        column_map["total_options"] = col_idx
        col_idx += 1
    
    if include_choice_one:
        columns.append("choice_answer_one")
        labels.append("choice answer one")
        column_map["choice_answer_one"] = col_idx
        col_idx += 1
    
    if include_choice_two:
        columns.append("choice_answer_two")
        labels.append("choice answer two")
        column_map["choice_answer_two"] = col_idx
        col_idx += 1
    
    if include_choice_three:
        columns.append("choice_answer_three")
        labels.append("choice answer three")
        column_map["choice_answer_three"] = col_idx
        col_idx += 1
    
    if include_choice_four:
        columns.append("choice_answer_four")
        labels.append("choice answer four")
        column_map["choice_answer_four"] = col_idx
        col_idx += 1
    
    if include_correct_answers:
        columns.append("correct_answers")
        labels.append("correct answers")
        column_map["correct_answers"] = col_idx
        col_idx += 1
    
    if include_tags:
        columns.append("tag1")
        labels.append("tag1")
        column_map["tag1"] = col_idx
        col_idx += 1
        columns.append("tag2")
        labels.append("tag2")
        column_map["tag2"] = col_idx
        col_idx += 1
    
    num_cols = len(columns)

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
    
    # Row 1: Subject header (merged across all columns)
    ws.write(0, 0, subject_name, subject_fmt)
    for col in range(1, num_cols):
        ws.write(0, col, '', subject_fmt)
    
    # Row 2: Column labels
    ws.write(1, 0, topic_name, label_fmt)
    for col, label in enumerate(labels, start=1):
        ws.write(1, col, label, label_fmt)
    
    # Rows 3+: Data
    for row_idx, r in enumerate(rows, start=2):
        data_row = [""] * num_cols
        data_row[0] = r.get("question", "")
        
        for col_name in columns[1:]:  # Skip question (already set)
            if col_name in column_map:
                col_pos = column_map[col_name]
                value = r.get(col_name, "")
                data_row[col_pos] = value
        
        for col, value in enumerate(data_row):
            ws.write(row_idx, col, value, data_fmt)
    
    # Set column widths
    ws.set_column(0, 0, 20)  # question
    ws.set_column(1, num_cols - 1, 15)  # other columns
    
    # Set row heights
    ws.set_row(0, 18)
    ws.set_row(1, 20)
    for i in range(2, len(rows) + 2):
        ws.set_row(i, 35)
    
    workbook.close()

    return xlsx_path

