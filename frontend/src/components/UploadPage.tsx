import { useState } from "react";

type EmbedResponse = {
  ok: boolean;
  subjectId: string;
  topicId: string;
  docName: string;
  uploadedBy: string;
  chunks_processed: number;
  embedding_model?: string;
  message: string;
};

interface UploadPageProps {
  apiUrl: string;
}

export default function UploadPage({ apiUrl }: UploadPageProps) {
  const [uploadType, setUploadType] = useState<"file" | "directory">("file");
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [docName, setDocName] = useState("");
  const [uploadedBy, setUploadedBy] = useState("user");
  const [file, setFile] = useState<File | null>(null);
  const [directoryPath, setDirectoryPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EmbedResponse | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    setFile(selectedFile || null);
    if (selectedFile) {
      setDocName(selectedFile.name);
    }
  };

  const uploadFile = async () => {
    if (!file || !subjectId || !topicId) {
      alert("Please fill in all required fields and select a file");
      return;
    }

    setBusy(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("subjectId", subjectId);
      formData.append("topicId", topicId);
      formData.append("docName", docName);
      formData.append("uploadedBy", uploadedBy);

      const response = await fetch(`${apiUrl}/api/chatbot/knowledge/upload-file`, {
        method: "POST",
        body: formData,
      });

      const data: EmbedResponse = await response.json();
      setResult(data);
    } catch (error: any) {
      setResult({
        ok: false,
        subjectId,
        topicId,
        docName,
        uploadedBy,
        chunks_processed: 0,
        message: `Error: ${error.message}`,
      });
    } finally {
      setBusy(false);
    }
  };

  const uploadDirectory = async () => {
    if (!directoryPath || !subjectId || !topicId) {
      alert("Please fill in all required fields and directory path");
      return;
    }

    setBusy(true);
    setResult(null);

    try {
      const response = await fetch(`${apiUrl}/api/chatbot/knowledge/ingest-dir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dirPath: directoryPath,
          subjectId,
          topicId,
          uploadedBy,
          recursive,
        }),
      });

      const data: EmbedResponse = await response.json();
      setResult(data);
    } catch (error: any) {
      setResult({
        ok: false,
        subjectId,
        topicId,
        docName: "",
        uploadedBy,
        chunks_processed: 0,
        message: `Error: ${error.message}`,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: "0 0 8px", fontSize: 24, fontWeight: 600 }}>
          Upload to Knowledge Base
        </h2>
        <p style={{ margin: 0, color: "#666", fontSize: 14 }}>
          Add documents to the knowledge base for internal mode queries. Supports PDF, DOCX, PPTX, TXT, and MD files.
        </p>
      </div>

      {/* Upload Type Selection */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, display: "block" }}>
          Upload Type
        </label>
        <div style={{ display: "flex", gap: 12 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input
              type="radio"
              name="uploadType"
              value="file"
              checked={uploadType === "file"}
              onChange={(e) => setUploadType(e.target.value as "file" | "directory")}
            />
            Single File
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input
              type="radio"
              name="uploadType"
              value="directory"
              checked={uploadType === "directory"}
              onChange={(e) => setUploadType(e.target.value as "file" | "directory")}
            />
            Directory
          </label>
        </div>
      </div>

      {/* Metadata Fields */}
      <div style={{
        background: "#f8f9fa",
        padding: 20,
        borderRadius: 8,
        border: "1px solid #e9ecef",
        marginBottom: 24,
      }}>
        <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
          Metadata
        </h3>
        
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Subject ID *
            </label>
            <input
              type="text"
              value={subjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              placeholder="e.g., data_structures"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Topic ID *
            </label>
            <input
              type="text"
              value={topicId}
              onChange={(e) => setTopicId(e.target.value)}
              placeholder="e.g., stacks_queues"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
        </div>

        {uploadType === "file" && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Document Name
            </label>
            <input
              type="text"
              value={docName}
              onChange={(e) => setDocName(e.target.value)}
              placeholder="Auto-filled from file name"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
        )}

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
            Uploaded By
          </label>
          <input
            type="text"
            value={uploadedBy}
            onChange={(e) => setUploadedBy(e.target.value)}
            placeholder="Your name or identifier"
            style={{
              width: "100%",
              padding: 8,
              border: "1px solid #ccc",
              borderRadius: 4,
              fontSize: 14,
            }}
          />
        </div>
      </div>

      {/* File Upload */}
      {uploadType === "file" && (
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          marginBottom: 24,
        }}>
          <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
            File Upload
          </h3>
          
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Select File *
            </label>
            <input
              type="file"
              onChange={handleFileChange}
              accept=".pdf,.docx,.pptx,.txt,.md"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
              Supported formats: PDF, DOCX, PPTX, TXT, MD
            </div>
          </div>

          {file && (
            <div style={{
              padding: 12,
              background: "#e6f6ec",
              borderRadius: 4,
              border: "1px solid #c3e6cb",
              marginBottom: 16,
            }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#0a7a3d" }}>
                Selected: {file.name}
              </div>
              <div style={{ fontSize: 12, color: "#666" }}>
                Size: {(file.size / 1024 / 1024).toFixed(2)} MB
              </div>
            </div>
          )}

          <button
            onClick={uploadFile}
            disabled={busy || !file || !subjectId || !topicId}
            style={{
              padding: "12px 24px",
              background: busy ? "#ccc" : "#28a745",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: busy ? "not-allowed" : "pointer",
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            {busy ? "Uploading..." : "Upload File"}
          </button>
        </div>
      )}

      {/* Directory Upload */}
      {uploadType === "directory" && (
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          marginBottom: 24,
        }}>
          <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
            Directory Upload
          </h3>
          
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Directory Path *
            </label>
            <input
              type="text"
              value={directoryPath}
              onChange={(e) => setDirectoryPath(e.target.value)}
              placeholder="/path/to/documents"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
              Absolute path to directory containing documents
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={recursive}
                onChange={(e) => setRecursive(e.target.checked)}
              />
              <span style={{ fontSize: 14 }}>Include subdirectories</span>
            </label>
          </div>

          <button
            onClick={uploadDirectory}
            disabled={busy || !directoryPath || !subjectId || !topicId}
            style={{
              padding: "12px 24px",
              background: busy ? "#ccc" : "#28a745",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: busy ? "not-allowed" : "pointer",
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            {busy ? "Processing..." : "Upload Directory"}
          </button>
        </div>
      )}

      {/* Results */}
      {result && (
        <div style={{
          padding: 20,
          borderRadius: 8,
          border: `1px solid ${result.ok ? "#c3e6cb" : "#f5c6cb"}`,
          background: result.ok ? "#d4edda" : "#f8d7da",
        }}>
          <h3 style={{ 
            margin: "0 0 12px", 
            fontSize: 18, 
            fontWeight: 600,
            color: result.ok ? "#0a7a3d" : "#721c24"
          }}>
            {result.ok ? "✅ Upload Successful" : "❌ Upload Failed"}
          </h3>
          
          <div style={{ fontSize: 14, lineHeight: 1.5 }}>
            <div><strong>Message:</strong> {result.message}</div>
            {result.ok && (
              <>
                <div><strong>Chunks Processed:</strong> {result.chunks_processed}</div>
                <div><strong>Subject ID:</strong> {result.subjectId}</div>
                <div><strong>Topic ID:</strong> {result.topicId}</div>
                {result.docName && <div><strong>Document:</strong> {result.docName}</div>}
                {result.embedding_model && (
                  <div><strong>Model:</strong> {result.embedding_model}</div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Help Section */}
      <div style={{
        background: "#e7f3ff",
        padding: 20,
        borderRadius: 8,
        border: "1px solid #b3d9ff",
        marginTop: 24,
      }}>
        <h4 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 600, color: "#0066cc" }}>
          💡 Tips
        </h4>
        <ul style={{ margin: 0, paddingLeft: 20, fontSize: 14, lineHeight: 1.5, color: "#333" }}>
          <li>Use descriptive Subject and Topic IDs for better organization</li>
          <li>Documents will be automatically chunked and embedded</li>
          <li>Uploaded content will be available in Internal mode chat</li>
          <li>Large files may take several minutes to process</li>
          <li>Check the console for detailed processing logs</li>
        </ul>
      </div>
    </div>
  );
}
