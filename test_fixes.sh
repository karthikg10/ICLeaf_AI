#!/bin/bash
# Test script for all fixes

API_URL="http://localhost:8000/api"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Testing ICLeaF AI Fixes"
echo "=========================================="
echo ""

# Test 1: API Key Loading
echo -e "${YELLOW}Test 1: API Key Loading${NC}"
echo "Checking if API key is loaded..."
curl -s "$API_URL/health" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('components', {}).get('openai_client', {}).get('status') == 'configured':
    print('✅ API key is loaded')
else:
    print('❌ API key is not loaded')
" 2>/dev/null || echo "❌ Health check failed"
echo ""

# Test 2: File Upload Persistence
echo -e "${YELLOW}Test 2: File Upload Persistence${NC}"
echo "Uploading test file..."
TEST_FILE="/tmp/test_upload_$(date +%s).txt"
echo "Test content for upload" > "$TEST_FILE"
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/chatbot/knowledge/upload-file" \
  -F "file=@$TEST_FILE" \
  -F "subjectId=test_subject" \
  -F "topicId=test_topic" \
  -F "uploadedBy=test_user")

echo "$UPLOAD_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('ok') or data.get('success'):
    print('✅ File uploaded successfully')
    print(f'   Chunks processed: {data.get(\"chunks_processed\", 0)}')
else:
    print('❌ File upload failed')
    print(f'   Error: {data.get(\"message\", \"Unknown error\")}')
" 2>/dev/null || echo "❌ Upload test failed"

sleep 2
echo "Checking if file was saved to /uploads..."
UPLOAD_COUNT=$(find backend/data/uploads -name "*.txt" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$UPLOAD_COUNT" -gt 0 ]; then
    echo "✅ Files found in uploads directory: $UPLOAD_COUNT"
    ls -lh backend/data/uploads/*.txt 2>/dev/null | tail -1 | awk '{print "   File: " $9 " (" $5 ")"}'
else
    echo "❌ No files found in uploads directory"
fi
echo ""

# Test 3: Chatbot Context Extraction
echo -e "${YELLOW}Test 3: Chatbot Context Extraction${NC}"
echo "Testing internal search..."
SEARCH_RESPONSE=$(curl -s "$API_URL/internal/search?q=data+structures&top_k=3")
SOURCE_COUNT=$(echo "$SEARCH_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
results = data.get('results', [])
print(len(results))
" 2>/dev/null || echo "0")

if [ "$SOURCE_COUNT" -gt 0 ]; then
    echo "✅ Found $SOURCE_COUNT relevant documents"
    echo "$SEARCH_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for i, r in enumerate(data.get('results', [])[:3], 1):
    print(f'   {i}. {r.get(\"title\", \"Unknown\")} (score: {r.get(\"score\", 0):.3f})')
" 2>/dev/null
else
    echo "❌ No documents found"
fi
echo ""

# Test 4: PDF Generation (Duplicate Folder Fix)
echo -e "${YELLOW}Test 4: PDF Generation (Duplicate Folder Fix)${NC}"
echo "Generating PDF with config..."
PDF_RESPONSE=$(curl -s -X POST "$API_URL/content/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test_user_fix",
    "role": "student",
    "mode": "internal",
    "contentType": "pdf",
    "prompt": "Generate a 2-page PDF about Python programming basics",
    "contentConfig": {
      "pdf": {
        "num_pages": 2,
        "target_audience": "students",
        "include_images": false,
        "difficulty": "beginner"
      }
    }
  }')

CONTENT_ID=$(echo "$PDF_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('contentId', ''))
" 2>/dev/null || echo "")

if [ -n "$CONTENT_ID" ]; then
    echo "✅ PDF generation started"
    echo "   Content ID: $CONTENT_ID"
    
    sleep 5  # Wait for generation
    
    echo "Checking folder structure..."
    USER_DIR="backend/data/content/test_user_fix"
    if [ -d "$USER_DIR" ]; then
        FOLDERS=$(find "$USER_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
        echo "   Folders found: $FOLDERS"
        
        if [ "$FOLDERS" -eq 1 ]; then
            echo "✅ Only one folder created (fix working!)"
            FOLDER=$(find "$USER_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)
            FILES=$(find "$FOLDER" -type f | wc -l | tr -d ' ')
            echo "   Files in folder: $FILES"
            
            if [ -f "$FOLDER/document.pdf" ]; then
                echo "✅ PDF file found in folder"
                PDF_SIZE=$(stat -f%z "$FOLDER/document.pdf" 2>/dev/null || stat -c%s "$FOLDER/document.pdf" 2>/dev/null || echo "0")
                echo "   PDF size: $PDF_SIZE bytes"
            else
                echo "❌ PDF file not found in folder"
                ls -la "$FOLDER" 2>/dev/null
            fi
        else
            echo "❌ Multiple folders found (duplicate folder issue still exists)"
            find "$USER_DIR" -mindepth 1 -maxdepth 1 -type d
        fi
    else
        echo "❌ User directory not found"
    fi
else
    echo "❌ PDF generation failed"
    echo "$PDF_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PDF_RESPONSE"
fi
echo ""

# Test 5: PPT Generation
echo -e "${YELLOW}Test 5: PPT Generation (Duplicate Folder Fix)${NC}"
echo "Generating PPT with config..."
PPT_RESPONSE=$(curl -s -X POST "$API_URL/content/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test_user_fix",
    "role": "student",
    "mode": "internal",
    "contentType": "ppt",
    "prompt": "Create a 5-slide presentation about machine learning",
    "contentConfig": {
      "ppt": {
        "num_slides": 5,
        "target_audience": "students",
        "include_animations": false,
        "difficulty": "beginner"
      }
    }
  }')

PPT_CONTENT_ID=$(echo "$PPT_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('contentId', ''))
" 2>/dev/null || echo "")

if [ -n "$PPT_CONTENT_ID" ]; then
    echo "✅ PPT generation started"
    echo "   Content ID: $PPT_CONTENT_ID"
    
    sleep 5  # Wait for generation
    
    echo "Checking folder structure..."
    PPT_FOLDER="backend/data/content/test_user_fix/$PPT_CONTENT_ID"
    if [ -d "$PPT_FOLDER" ]; then
        FILES=$(find "$PPT_FOLDER" -type f | wc -l | tr -d ' ')
        echo "   Files in folder: $FILES"
        
        if [ -f "$PPT_FOLDER/presentation.pptx" ]; then
            echo "✅ PPT file found in folder"
            PPT_SIZE=$(stat -f%z "$PPT_FOLDER/presentation.pptx" 2>/dev/null || stat -c%s "$PPT_FOLDER/presentation.pptx" 2>/dev/null || echo "0")
            echo "   PPT size: $PPT_SIZE bytes"
        else
            echo "❌ PPT file not found in folder"
            ls -la "$PPT_FOLDER" 2>/dev/null
        fi
    else
        echo "❌ PPT folder not found"
    fi
else
    echo "❌ PPT generation failed"
    echo "$PPT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PPT_RESPONSE"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "✅ Fix #1: API Key Loading - Tested"
echo "✅ Fix #2: File Upload Persistence - Tested"
echo "✅ Fix #3: Chatbot Context Extraction - Tested"
echo "✅ Fix #4: PDF Generation (Duplicate Folders) - Tested"
echo "✅ Fix #5: PPT Generation (Duplicate Folders) - Tested"
echo ""
echo "Check the results above for detailed status."
echo ""


