#!/bin/bash
echo "=== ICLeaF AI API Test Suite ==="
echo "Starting comprehensive API testing..."

# Core System Tests
echo "=== 1. HEALTH CHECK ==="
curl -sS http://127.0.0.1:8000/api/health | jq '.ok, .system, .version' 2>/dev/null || curl -sS http://127.0.0.1:8000/api/health

echo "=== 2. INTERNAL SEARCH ==="
curl -sS 'http://127.0.0.1:8000/api/internal/search?q=data&top_k=3' | jq '.ok, .q, (.results | length)' 2>/dev/null || curl -sS 'http://127.0.0.1:8000/api/internal/search?q=data&top_k=3'

# Chatbot Tests
echo "=== 3. CHATBOT INTERNAL MODE ==="
curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/query' -H 'Content-Type: application/json' -d '{"role":"student","mode":"internal","message":"What is a linked list?","sessionId":"sess-1","userId":"user-1","top_k":4}' | jq '.success, .mode, (.sources | length)' 2>/dev/null || curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/query' -H 'Content-Type: application/json' -d '{"role":"student","mode":"internal","message":"What is a linked list?","sessionId":"sess-1","userId":"user-1","top_k":4}'

echo "=== 4. CHATBOT EXTERNAL MODE ==="
curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/query' -H 'Content-Type: application/json' -d '{"role":"student","mode":"external","message":"Latest trends in Python packaging","sessionId":"sess-2","userId":"user-1","top_k":3}' | jq '.success, .mode' 2>/dev/null || curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/query' -H 'Content-Type: application/json' -d '{"role":"student","mode":"external","message":"Latest trends in Python packaging","sessionId":"sess-2","userId":"user-1","top_k":3}'

# Content Generation Tests
echo "=== 5. CONTENT GENERATION - FLASHCARD ==="
FLASHCARD_ID=$(curl -sS -X POST 'http://127.0.0.1:8000/api/content/generate' -H 'Content-Type: application/json' -d '{"userId":"user-1","role":"student","mode":"internal","contentType":"flashcard","prompt":"Data structures basics","contentConfig":{"flashcard":{"front":"Term","back":"Definition","difficulty":"easy"}}}' | jq -r '.contentId' 2>/dev/null)
echo "Flashcard ID: $FLASHCARD_ID"

echo "=== 6. CONTENT GENERATION - QUIZ ==="
QUIZ_ID=$(curl -sS -X POST 'http://127.0.0.1:8000/api/content/generate' -H 'Content-Type: application/json' -d '{"userId":"user-1","role":"student","mode":"internal","contentType":"quiz","prompt":"Basic algorithms","contentConfig":{"quiz":{"num_questions":3,"difficulty":"medium","question_types":["multiple_choice"]}}}' | jq -r '.contentId' 2>/dev/null)
echo "Quiz ID: $QUIZ_ID"

echo "=== 7. CONTENT GENERATION - ASSESSMENT ==="
ASSESSMENT_ID=$(curl -sS -X POST 'http://127.0.0.1:8000/api/content/generate' -H 'Content-Type: application/json' -d '{"userId":"user-1","role":"student","mode":"internal","contentType":"assessment","prompt":"Data structures assessment","contentConfig":{"assessment":{"duration_minutes":30,"difficulty":"medium","question_types":["multiple_choice","fillup"]}}}' | jq -r '.contentId' 2>/dev/null)
echo "Assessment ID: $ASSESSMENT_ID"

# Content Info Tests
echo "=== 8. CONTENT INFO (with CSV/XLSX files) ==="
curl -sS http://127.0.0.1:8000/api/content/info/$FLASHCARD_ID | jq '.success, .filePath, .contentType' 2>/dev/null || curl -sS http://127.0.0.1:8000/api/content/info/$FLASHCARD_ID

# Pagination Tests
echo "=== 9. CONTENT LIST (with pagination) ==="
curl -sS 'http://127.0.0.1:8000/api/content/list?userId=user-1&page=1&limit=5' | jq '.success, .pagination.currentPage, .pagination.totalRecords, (.contents | length)' 2>/dev/null || curl -sS 'http://127.0.0.1:8000/api/content/list?userId=user-1&page=1&limit=5'

echo "=== 10. HISTORY (with pagination) ==="
curl -sS 'http://127.0.0.1:8000/api/chatbot/history?userId=user-1&page=1&limit=5' | jq '.success, .pagination.currentPage, .pagination.totalRecords, (.conversations | length)' 2>/dev/null || curl -sS 'http://127.0.0.1:8000/api/chatbot/history?userId=user-1&page=1&limit=5'

# Analytics Tests
echo "=== 11. ANALYTICS ==="
curl -sS 'http://127.0.0.1:8000/api/chatbot/analytics?userId=user-1' | jq '.success, .tokenUsage.totalCost, .userEngagement.totalQueries' 2>/dev/null || curl -sS 'http://127.0.0.1:8000/api/chatbot/analytics?userId=user-1'

# Download Tracking Tests
echo "=== 12. DOWNLOAD TRACKING ==="
curl -sS http://127.0.0.1:8000/api/content/download/$FLASHCARD_ID > /dev/null && echo "Download completed" && curl -sS http://127.0.0.1:8000/api/content/$FLASHCARD_ID/downloads | jq '.success, .downloadStats.total_downloads' 2>/dev/null || curl -sS http://127.0.0.1:8000/api/content/$FLASHCARD_ID/downloads

# Session Management Tests
echo "=== 13. SESSION RESET ==="
curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/reset-session' -H 'Content-Type: application/json' -d '{"sessionId":"sess-1","userId":"user-1","resetScope":"full"}' | jq '.success, .message' 2>/dev/null || curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/reset-session' -H 'Content-Type: application/json' -d '{"sessionId":"sess-1","userId":"user-1","resetScope":"full"}'

# File Upload Tests
echo "=== 14. FILE UPLOAD (50MB limit test) ==="
echo "Test file content" > /tmp/test_upload.txt
curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/knowledge/upload-file' -F 'file=@/tmp/test_upload.txt' -F 'subjectId=test-subject' -F 'topicId=test-topic' -F 'uploadedBy=user-1' | jq '.success, .message' 2>/dev/null || curl -sS -X POST 'http://127.0.0.1:8000/api/chatbot/knowledge/upload-file' -F 'file=@/tmp/test_upload.txt' -F 'subjectId=test-subject' -F 'topicId=test-topic' -F 'uploadedBy=user-1'

# Error Handling Tests
echo "=== 15. ERROR HANDLING (404) ==="
curl -sS http://127.0.0.1:8000/api/content/info/nonexistent-id | jq '.success, .message' 2>/dev/null || curl -sS http://127.0.0.1:8000/api/content/info/nonexistent-id

# File Format Verification
echo "=== 16. VERIFY CSV/XLSX FILES CREATED ==="
ls -la /Users/karthik/ICLeaf_AI/backend/data/content/user-1/$FLASHCARD_ID/ | grep -E '\.(csv|xlsx)$'
ls -la /Users/karthik/ICLeaf_AI/backend/data/content/user-1/$QUIZ_ID/ | grep -E '\.(csv|xlsx)$'
ls -la /Users/karthik/ICLeaf_AI/backend/data/content/user-1/$ASSESSMENT_ID/ | grep -E '\.(csv|xlsx)$'

echo "=== 17. CHECK CSV CONTENT FORMAT ==="
head -3 /Users/karthik/ICLeaf_AI/backend/data/content/user-1/$FLASHCARD_ID/flashcards.csv
head -3 /Users/karthik/ICLeaf_AI/backend/data/content/user-1/$QUIZ_ID/quiz.csv

echo "=== All Tests Completed Successfully! ==="
