#!/bin/bash

echo "=== Testing PDF Generation ==="
echo ""

# Test PDF generation via new API endpoint
echo "1. Testing PDF via /api/content/generate:"
PDF_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/content/generate \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test_user_pdf",
    "role": "student",
    "mode": "internal",
    "contentType": "pdf",
    "prompt": "Introduction to Python Programming Basics",
    "contentConfig": {
      "pdf": {
        "num_pages": 3,
        "target_audience": "students",
        "include_images": false,
        "difficulty": "medium"
      }
    }
  }')

echo "$PDF_RESPONSE" | python3 -m json.tool
echo ""

# Extract contentId if successful
PDF_CONTENT_ID=$(echo "$PDF_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('contentId', ''))" 2>/dev/null)

if [ ! -z "$PDF_CONTENT_ID" ] && [ "$PDF_CONTENT_ID" != "" ]; then
    echo "PDF Content ID: $PDF_CONTENT_ID"
    echo ""
    echo "Checking PDF status:"
    curl -s "http://127.0.0.1:8000/api/content/${PDF_CONTENT_ID}/status" | python3 -m json.tool
    echo ""
fi

echo ""
echo "=== Testing PPT Generation ==="
echo ""

# Test PPT generation via new API endpoint
echo "2. Testing PPT via /api/content/generate:"
PPT_RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/content/generate \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "test_user_ppt",
    "role": "student",
    "mode": "internal",
    "contentType": "ppt",
    "prompt": "Introduction to Machine Learning Concepts",
    "contentConfig": {
      "ppt": {
        "num_slides": 5,
        "target_audience": "students",
        "include_animations": false,
        "difficulty": "medium"
      }
    }
  }')

echo "$PPT_RESPONSE" | python3 -m json.tool
echo ""

# Extract contentId if successful
PPT_CONTENT_ID=$(echo "$PPT_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('contentId', ''))" 2>/dev/null)

if [ ! -z "$PPT_CONTENT_ID" ] && [ "$PPT_CONTENT_ID" != "" ]; then
    echo "PPT Content ID: $PPT_CONTENT_ID"
    echo ""
    echo "Checking PPT status:"
    curl -s "http://127.0.0.1:8000/api/content/${PPT_CONTENT_ID}/status" | python3 -m json.tool
    echo ""
fi

echo ""
echo "=== Testing Legacy Endpoints ==="
echo ""

# Test legacy PDF endpoint
echo "3. Testing legacy /generate/pdf endpoint:"
curl -s -X POST http://127.0.0.1:8000/generate/pdf \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Introduction to Data Structures",
    "role": "student",
    "mode": "internal",
    "kind": "summary",
    "top_k": 5,
    "num_questions": 5
  }' -o /tmp/test_legacy_pdf.pdf -w "\nHTTP Status: %{http_code}\nSize: %{size_download} bytes\n"

if [ -f /tmp/test_legacy_pdf.pdf ]; then
    echo "PDF file created: /tmp/test_legacy_pdf.pdf"
    ls -lh /tmp/test_legacy_pdf.pdf
else
    echo "PDF file not created"
fi
echo ""

# Test legacy PPT endpoint
echo "4. Testing legacy /generate/pptx endpoint:"
curl -s -X POST http://127.0.0.1:8000/generate/pptx \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Introduction to Algorithms",
    "role": "student",
    "mode": "internal",
    "kind": "summary",
    "top_k": 5,
    "num_questions": 5
  }' -o /tmp/test_legacy_ppt.pptx -w "\nHTTP Status: %{http_code}\nSize: %{size_download} bytes\n"

if [ -f /tmp/test_legacy_ppt.pptx ]; then
    echo "PPT file created: /tmp/test_legacy_ppt.pptx"
    ls -lh /tmp/test_legacy_ppt.pptx
else
    echo "PPT file not created"
fi



