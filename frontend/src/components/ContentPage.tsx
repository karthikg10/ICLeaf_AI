import { useState, useEffect } from "react";

type Role = "student" | "teacher" | "admin";
type Mode = "internal" | "external";
type ContentType = "pdf" | "ppt" | "flashcard" | "quiz" | "assessment" | "video" | "audio" | "compiler";
type ContentStatus = "pending" | "completed" | "failed";

type GeneratedContent = {
  contentId: string;
  userId: string;
  role: Role;
  mode: Mode;
  contentType: ContentType;
  prompt: string;
  status: ContentStatus;
  createdAt: string;
  completedAt?: string;
  filePath?: string;
  downloadUrl?: string;
  contentConfig: any;
  metadata: any;
  error?: string;
};

type GenerateContentResponse = {
  ok: boolean;
  contentId: string;
  userId: string;
  status: ContentStatus;
  message: string;
  estimated_completion_time?: number;
  metadata?: {
    rag_metadata?: {
      documents_used?: string[];
      num_blocks?: number;
      requested_docIds?: string[];
      internal_mode?: boolean;
      rag_used?: boolean;
      error?: string;
    };
  };
};

type ContentListResponse = {
  ok: boolean;
  content: GeneratedContent[];
  total_count: number;
  userId: string;
};

type ContentDownloadResponse = {
  ok: boolean;
  contentId: string;
  filePath: string;
  downloadUrl?: string;
  contentType: string;
  fileSize?: number;
  message?: string;
};

interface ContentPageProps {
  role: Role;
  mode: Mode;
  apiUrl: string;
}

export default function ContentPage({ role, mode, apiUrl }: ContentPageProps) {
  const [activeTab, setActiveTab] = useState<"generate" | "list">("generate");
  const [userId] = useState(() => `user_${Date.now()}`);
  
  // Generation state
  const [contentType, setContentType] = useState<ContentType>("pdf");
  const [prompt, setPrompt] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [topicName, setTopicName] = useState("");
  const [docIds, setDocIds] = useState<string>(""); // Comma-separated docIds for internal mode
  const [generating, setGenerating] = useState(false);
  const [generationResult, setGenerationResult] = useState<GenerateContentResponse | null>(null);
  
  // Content configs
  const [flashcardConfig, setFlashcardConfig] = useState({
    front: "",
    back: "",
    difficulty: "medium" as "easy" | "medium" | "hard"
  });
  const [quizConfig, setQuizConfig] = useState({
    num_questions: 5,
    difficulty: "medium" as "easy" | "medium" | "hard",
    question_types: ["multiple_choice", "true_false"] as string[]
  });
  const [assessmentConfig] = useState({
    duration_minutes: 30,
    difficulty: "medium" as "easy" | "medium" | "hard",
    question_types: ["multiple_choice", "essay"] as string[],
    passing_score: 70
  });
  const [videoConfig] = useState({
    duration_seconds: 60,
    quality: "720p" as "480p" | "720p" | "1080p",
    include_subtitles: true
  });
  const [audioConfig, setAudioConfig] = useState({
    duration_seconds: 300,
    quality: "high" as "low" | "medium" | "high",
    format: "mp3" as "mp3" | "wav" | "ogg",
    voice_type: "female" as "male" | "female",
    target_audience: "general" as "children" | "students" | "professionals" | "general"
  });
  const [pdfConfig, setPdfConfig] = useState({
    num_pages: 5,
    target_audience: "general" as "children" | "students" | "professionals" | "general",
    include_images: true,
    difficulty: "medium" as "easy" | "medium" | "hard"
  });
  const [pptConfig, setPptConfig] = useState({
    num_slides: 10,
    target_audience: "general" as "children" | "students" | "professionals" | "general",
    include_animations: true,
    difficulty: "medium" as "easy" | "medium" | "hard"
  });
  const [compilerConfig] = useState({
    language: "python" as "python" | "javascript" | "java" | "cpp",
    include_tests: true,
    difficulty: "medium" as "easy" | "medium" | "hard"
  });
  
  // List state
  const [contentList, setContentList] = useState<GeneratedContent[]>([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const generateContent = async () => {
    if (!prompt.trim()) {
      alert("Please enter a prompt");
      return;
    }

    setGenerating(true);
    setGenerationResult(null);

    try {
      const contentConfig: any = {};
      
      // Set config based on content type
      switch (contentType) {
        case "flashcard":
          contentConfig.flashcard = flashcardConfig;
          break;
        case "quiz":
          contentConfig.quiz = quizConfig;
          break;
        case "assessment":
          contentConfig.assessment = assessmentConfig;
          break;
        case "video":
          contentConfig.video = videoConfig;
          break;
        case "audio":
          contentConfig.audio = audioConfig;
          break;
        case "pdf":
          contentConfig.pdf = pdfConfig;
          break;
        case "ppt":
          contentConfig.ppt = pptConfig;
          break;
        case "compiler":
          contentConfig.compiler = compilerConfig;
          break;
      }

      const requestBody: any = {
        userId,
        role,
        mode,
        contentType,
        prompt: prompt.trim(),
        contentConfig
      };

      // Debug: Log the configuration being sent
      console.log('Sending configuration:', contentConfig);

      // Add mode-specific fields
      if (mode === "internal") {
        // For internal mode, parse docIds from comma-separated string
        if (docIds.trim()) {
          requestBody.docIds = docIds.split(',').map(id => id.trim()).filter(id => id.length > 0);
        } else {
          requestBody.docIds = [];
        }
      } else {
        // For external mode
        if (subjectName) requestBody.subjectName = subjectName;
        if (topicName) requestBody.topicName = topicName;
      }

      const response = await fetch(`${apiUrl}/api/content/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });

      const data: GenerateContentResponse = await response.json();
      setGenerationResult(data);
      
      if (data.ok) {
        // Refresh content list
        fetchContentList();
        
        // Reset configuration to defaults after successful generation
        if (contentType === "pdf") {
          setPdfConfig({
            num_pages: 5,
            target_audience: "general",
            include_images: true,
            difficulty: "medium"
          });
        } else if (contentType === "ppt") {
          setPptConfig({
            num_slides: 10,
            target_audience: "general",
            include_animations: true,
            difficulty: "medium"
          });
        } else if (contentType === "audio") {
          setAudioConfig({
            duration_seconds: 300,
            quality: "high",
            format: "mp3",
            voice_type: "female",
            target_audience: "general"
          });
        }
      }
    } catch (error: any) {
      setGenerationResult({
        ok: false,
        contentId: "",
        userId,
        status: "failed",
        message: `Error: ${error.message}`
      });
    } finally {
      setGenerating(false);
    }
  };

  const fetchContentList = async () => {
    setLoading(true);
    setListError(null);

    try {
      const response = await fetch(`${apiUrl}/api/content/list?userId=${userId}`);
      const data: ContentListResponse = await response.json();

      if (data.ok) {
        setContentList(data.content);
      } else {
        setListError("Failed to fetch content list");
      }
    } catch (error: any) {
      setListError(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const downloadContent = async (contentId: string) => {
    try {
      const response = await fetch(`${apiUrl}/api/content/download/${contentId}`);
      const data: ContentDownloadResponse = await response.json();

      if (data.ok && data.downloadUrl) {
        window.open(data.downloadUrl, '_blank');
      } else {
        alert(data.message || "Download failed");
      }
    } catch (error: any) {
      alert(`Download error: ${error.message}`);
    }
  };

  const resetConfiguration = () => {
    if (contentType === "pdf") {
      setPdfConfig({
        num_pages: 5,
        target_audience: "general",
        include_images: true,
        difficulty: "medium"
      });
    } else if (contentType === "ppt") {
      setPptConfig({
        num_slides: 10,
        target_audience: "general",
        include_animations: true,
        difficulty: "medium"
      });
    } else if (contentType === "audio") {
      setAudioConfig({
        duration_seconds: 300,
        quality: "high",
        format: "mp3",
        voice_type: "female",
        target_audience: "general"
      });
    }
  };

  const getStatusColor = (status: ContentStatus) => {
    switch (status) {
      case "completed": return "#28a745";
      case "pending": return "#ffc107";
      case "failed": return "#dc3545";
      default: return "#6c757d";
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };


  useEffect(() => {
    if (activeTab === "list") {
      fetchContentList();
    }
  }, [activeTab]);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: "0 0 8px", fontSize: 24, fontWeight: 600 }}>
          Content Generation & Management
        </h2>
        <p style={{ margin: 0, color: "#666", fontSize: 14 }}>
          Generate various types of educational content and manage your content library.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ 
        display: "flex", 
        borderBottom: "1px solid #eee", 
        marginBottom: 24,
        gap: 0 
      }}>
        {[
          { id: "generate", label: "🎨 Generate", color: "#007bff" },
          { id: "list", label: "📋 My Content", color: "#28a745" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            style={{
              padding: "12px 20px",
              border: "none",
              borderBottom: activeTab === tab.id ? `3px solid ${tab.color}` : "3px solid transparent",
              background: "transparent",
              color: activeTab === tab.id ? tab.color : "#333",
              cursor: "pointer",
              fontWeight: activeTab === tab.id ? 600 : 400,
              fontSize: 14,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Generate Tab */}
      {activeTab === "generate" && (
        <div>
          {/* Content Type Selection */}
          <div style={{
            background: "#f8f9fa",
            padding: 20,
            borderRadius: 8,
            border: "1px solid #e9ecef",
            marginBottom: 24,
          }}>
            <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
              Content Type
            </h3>
            
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12 }}>
              {[
                { type: "pdf", label: "📄 PDF", desc: "Document" },
                { type: "ppt", label: "📊 PPT", desc: "Presentation" },
                { type: "flashcard", label: "🃏 Flashcard", desc: "Study cards" },
                { type: "quiz", label: "❓ Quiz", desc: "Questions" },
                { type: "assessment", label: "📝 Assessment", desc: "Test" },
                { type: "video", label: "🎥 Video", desc: "Script" },
                { type: "audio", label: "🎵 Audio", desc: "Recording" },
                { type: "compiler", label: "💻 Code", desc: "Programming" },
              ].map((option) => (
                <button
                  key={option.type}
                  onClick={() => setContentType(option.type as ContentType)}
                  style={{
                    padding: 16,
                    border: contentType === option.type ? "2px solid #007bff" : "2px solid #e9ecef",
                    borderRadius: 8,
                    background: contentType === option.type ? "#e8f1ff" : "#fff",
                    cursor: "pointer",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 16, marginBottom: 4 }}>{option.label}</div>
                  <div style={{ fontSize: 12, color: "#666" }}>{option.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Prompt Input */}
          <div style={{
            background: "#fff",
            padding: 20,
            borderRadius: 8,
            border: "1px solid #e9ecef",
            marginBottom: 24,
          }}>
            <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
              Content Prompt
            </h3>
            
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                Describe what you want to generate *
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={`Describe the ${contentType} you want to generate...`}
                rows={4}
                style={{
                  width: "100%",
                  padding: 12,
                  border: "1px solid #ccc",
                  borderRadius: 6,
                  fontSize: 14,
                  resize: "vertical",
                }}
              />
            </div>

            {mode === "external" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Subject Name
                  </label>
                  <input
                    type="text"
                    value={subjectName}
                    onChange={(e) => setSubjectName(e.target.value)}
                    placeholder="e.g., Data Structures"
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
                    Topic Name
                  </label>
                  <input
                    type="text"
                    value={topicName}
                    onChange={(e) => setTopicName(e.target.value)}
                    placeholder="e.g., Stacks and Queues"
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
            )}

            {mode === "internal" && (
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                  Document IDs (docIds) - Optional
                </label>
                <input
                  type="text"
                  value={docIds}
                  onChange={(e) => setDocIds(e.target.value)}
                  placeholder="Enter comma-separated docIds (e.g., doc-id-1, doc-id-2) or leave empty to use all documents"
                  style={{
                    width: "100%",
                    padding: 8,
                    border: "1px solid #ccc",
                    borderRadius: 4,
                    fontSize: 14,
                    fontFamily: "monospace",
                  }}
                />
                <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                  💡 Tip: Get docIds from the Upload page after uploading files. Enter multiple docIds separated by commas to generate content from specific documents only.
                </div>
              </div>
            )}
          </div>

          {/* Content Type Specific Configs */}
          {contentType === "flashcard" && (
            <div style={{
              background: "#fff",
              padding: 20,
              borderRadius: 8,
              border: "1px solid #e9ecef",
              marginBottom: 24,
            }}>
              <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
                Flashcard Configuration
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Front Text
                  </label>
                  <input
                    type="text"
                    value={flashcardConfig.front}
                    onChange={(e) => setFlashcardConfig({...flashcardConfig, front: e.target.value})}
                    placeholder="What's on the front?"
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
                    Back Text
                  </label>
                  <input
                    type="text"
                    value={flashcardConfig.back}
                    onChange={(e) => setFlashcardConfig({...flashcardConfig, back: e.target.value})}
                    placeholder="What's on the back?"
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
              <div style={{ marginTop: 16 }}>
                <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                  Difficulty
                </label>
                <select
                  value={flashcardConfig.difficulty}
                  onChange={(e) => setFlashcardConfig({...flashcardConfig, difficulty: e.target.value as any})}
                  style={{
                    padding: 8,
                    border: "1px solid #ccc",
                    borderRadius: 4,
                    fontSize: 14,
                  }}
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </div>
            </div>
          )}

          {contentType === "quiz" && (
            <div style={{
              background: "#fff",
              padding: 20,
              borderRadius: 8,
              border: "1px solid #e9ecef",
              marginBottom: 24,
            }}>
              <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
                Quiz Configuration
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Number of Questions
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={quizConfig.num_questions}
                    onChange={(e) => setQuizConfig({...quizConfig, num_questions: parseInt(e.target.value)})}
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
                    Difficulty
                  </label>
                  <select
                    value={quizConfig.difficulty}
                    onChange={(e) => setQuizConfig({...quizConfig, difficulty: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {contentType === "pdf" && (
            <div style={{
              background: "#fff",
              padding: 20,
              borderRadius: 8,
              border: "1px solid #e9ecef",
              marginBottom: 24,
            }}>
              <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
                PDF Configuration
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Number of Pages
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={pdfConfig.num_pages}
                    onChange={(e) => setPdfConfig({...pdfConfig, num_pages: parseInt(e.target.value)})}
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
                    Target Audience
                  </label>
                  <select
                    value={pdfConfig.target_audience}
                    onChange={(e) => setPdfConfig({...pdfConfig, target_audience: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="children">Children</option>
                    <option value="students">Students</option>
                    <option value="professionals">Professionals</option>
                    <option value="general">General</option>
                  </select>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Difficulty
                  </label>
                  <select
                    value={pdfConfig.difficulty}
                    onChange={(e) => setPdfConfig({...pdfConfig, difficulty: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                </div>
                <div style={{ display: "flex", alignItems: "center", marginTop: 20 }}>
                  <label style={{ display: "flex", alignItems: "center", fontSize: 14, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={pdfConfig.include_images}
                      onChange={(e) => setPdfConfig({...pdfConfig, include_images: e.target.checked})}
                      style={{ marginRight: 8 }}
                    />
                    Include Images
                  </label>
                </div>
              </div>
            </div>
          )}

          {contentType === "ppt" && (
            <div style={{
              background: "#fff",
              padding: 20,
              borderRadius: 8,
              border: "1px solid #e9ecef",
              marginBottom: 24,
            }}>
              <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
                PowerPoint Configuration
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Number of Slides
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={pptConfig.num_slides}
                    onChange={(e) => setPptConfig({...pptConfig, num_slides: parseInt(e.target.value)})}
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
                    Target Audience
                  </label>
                  <select
                    value={pptConfig.target_audience}
                    onChange={(e) => setPptConfig({...pptConfig, target_audience: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="children">Children</option>
                    <option value="students">Students</option>
                    <option value="professionals">Professionals</option>
                    <option value="general">General</option>
                  </select>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Difficulty
                  </label>
                  <select
                    value={pptConfig.difficulty}
                    onChange={(e) => setPptConfig({...pptConfig, difficulty: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                </div>
                <div style={{ display: "flex", alignItems: "center", marginTop: 20 }}>
                  <label style={{ display: "flex", alignItems: "center", fontSize: 14, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={pptConfig.include_animations}
                      onChange={(e) => setPptConfig({...pptConfig, include_animations: e.target.checked})}
                      style={{ marginRight: 8 }}
                    />
                    Include Animations
                  </label>
                </div>
              </div>
            </div>
          )}

          {contentType === "audio" && (
            <div style={{
              background: "#fff",
              padding: 20,
              borderRadius: 8,
              border: "1px solid #e9ecef",
              marginBottom: 24,
            }}>
              <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
                Audio Configuration
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Duration (seconds)
                  </label>
                  <input
                    type="number"
                    min="30"
                    max="3600"
                    value={audioConfig.duration_seconds}
                    onChange={(e) => setAudioConfig({...audioConfig, duration_seconds: parseInt(e.target.value)})}
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
                    Voice Type
                  </label>
                  <select
                    value={audioConfig.voice_type}
                    onChange={(e) => setAudioConfig({...audioConfig, voice_type: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                  </select>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Target Audience
                  </label>
                  <select
                    value={audioConfig.target_audience}
                    onChange={(e) => setAudioConfig({...audioConfig, target_audience: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="children">Children</option>
                    <option value="students">Students</option>
                    <option value="professionals">Professionals</option>
                    <option value="general">General</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Quality
                  </label>
                  <select
                    value={audioConfig.quality}
                    onChange={(e) => setAudioConfig({...audioConfig, quality: e.target.value as any})}
                    style={{
                      width: "100%",
                      padding: 8,
                      border: "1px solid #ccc",
                      borderRadius: 4,
                      fontSize: 14,
                    }}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Generate Button */}
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <button
              onClick={generateContent}
              disabled={generating || !prompt.trim()}
              style={{
                padding: "16px 32px",
                background: generating ? "#ccc" : "#007bff",
                color: "white",
                border: "none",
                borderRadius: 8,
                cursor: generating ? "not-allowed" : "pointer",
                fontWeight: 600,
                fontSize: 16,
                marginRight: 12,
              }}
            >
              {generating ? "Generating..." : `Generate ${contentType.toUpperCase()}`}
            </button>
            <button
              onClick={resetConfiguration}
              disabled={generating}
              style={{
                padding: "16px 24px",
                background: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: 8,
                cursor: generating ? "not-allowed" : "pointer",
                fontWeight: 600,
                fontSize: 16,
              }}
            >
              Reset Config
            </button>
          </div>

          {/* Generation Result */}
          {generationResult && (
            <div style={{
              padding: 20,
              borderRadius: 8,
              border: `1px solid ${generationResult.ok ? "#c3e6cb" : "#f5c6cb"}`,
              background: generationResult.ok ? "#d4edda" : "#f8d7da",
            }}>
              <h3 style={{ 
                margin: "0 0 12px", 
                fontSize: 18, 
                fontWeight: 600,
                color: generationResult.ok ? "#0a7a3d" : "#721c24"
              }}>
                {generationResult.ok ? "✅ Generation Started" : "❌ Generation Failed"}
              </h3>
              
              <div style={{ fontSize: 14, lineHeight: 1.5 }}>
                <div><strong>Message:</strong> {generationResult.message}</div>
                {generationResult.ok && (
                  <>
                    <div><strong>Content ID:</strong> {generationResult.contentId}</div>
                    <div><strong>Status:</strong> {generationResult.status}</div>
                    {generationResult.estimated_completion_time && (
                      <div><strong>Estimated Time:</strong> {generationResult.estimated_completion_time} seconds</div>
                    )}
                    {/* RAG Metadata Display for Internal Mode */}
                    {generationResult.metadata?.rag_metadata && (
                      <div style={{ marginTop: 16, padding: 12, background: "#f8f9fa", borderRadius: 4, border: "1px solid #dee2e6" }}>
                        <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>
                          📄 Document Usage (Internal Mode)
                        </div>
                        {generationResult.metadata.rag_metadata.rag_used ? (
                          <>
                            {generationResult.metadata.rag_metadata.documents_used && generationResult.metadata.rag_metadata.documents_used.length > 0 ? (
                              <div style={{ marginBottom: 8 }}>
                                <strong>Documents Used:</strong>{" "}
                                <span style={{ color: "#0a7a3d" }}>
                                  {generationResult.metadata.rag_metadata.documents_used.join(", ") || "None found"}
                                </span>
                              </div>
                            ) : (
                              <div style={{ marginBottom: 8, color: "#856404" }}>
                                <strong>⚠️ No documents found matching your request</strong>
                              </div>
                            )}
                            {generationResult.metadata.rag_metadata.requested_docIds && generationResult.metadata.rag_metadata.requested_docIds.length > 0 && (
                              <div style={{ marginBottom: 8, fontSize: 12, color: "#6c757d" }}>
                                <strong>Requested docIds:</strong> {generationResult.metadata.rag_metadata.requested_docIds.join(", ")}
                              </div>
                            )}
                            {generationResult.metadata.rag_metadata.num_blocks !== undefined && (
                              <div style={{ marginBottom: 8, fontSize: 12, color: "#6c757d" }}>
                                <strong>Context Blocks Retrieved:</strong> {generationResult.metadata.rag_metadata.num_blocks}
                              </div>
                            )}
                          </>
                        ) : (
                          <div style={{ color: "#856404" }}>
                            <strong>⚠️ RAG not used</strong>
                            {generationResult.metadata.rag_metadata.error && (
                              <div style={{ fontSize: 12, marginTop: 4 }}>
                                Error: {generationResult.metadata.rag_metadata.error}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* List Tab */}
      {activeTab === "list" && (
        <div>
          <div style={{ 
            display: "flex", 
            justifyContent: "space-between", 
            alignItems: "center", 
            marginBottom: 20 
          }}>
            <h3 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
              My Generated Content
            </h3>
            <button
              onClick={fetchContentList}
              disabled={loading}
              style={{
                padding: "8px 16px",
                background: loading ? "#ccc" : "#007bff",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: loading ? "not-allowed" : "pointer",
                fontSize: 14,
              }}
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {listError && (
            <div style={{
              padding: 16,
              background: "#f8d7da",
              color: "#721c24",
              borderRadius: 6,
              border: "1px solid #f5c6cb",
              marginBottom: 16,
            }}>
              {listError}
            </div>
          )}

          {contentList.length === 0 && !loading && (
            <div style={{ 
              textAlign: "center", 
              padding: 40, 
              color: "#666",
              fontSize: 16 
            }}>
              No content generated yet. Start by creating your first piece of content!
            </div>
          )}

          {contentList.length > 0 && (
            <div style={{
              background: "#fff",
              borderRadius: 8,
              border: "1px solid #e9ecef",
              overflow: "hidden",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "#f8f9fa", borderBottom: "1px solid #e9ecef" }}>
                      <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Type</th>
                      <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Prompt</th>
                      <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Status</th>
                      <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Created</th>
                      <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contentList.map((content, index) => (
                      <tr key={index} style={{ borderBottom: "1px solid #f1f3f4" }}>
                        <td style={{ padding: 12, fontSize: 14 }}>
                          <span style={{
                            padding: "4px 8px",
                            borderRadius: 12,
                            fontSize: 11,
                            fontWeight: 600,
                            background: "#e8f1ff",
                            color: "#175cd3",
                          }}>
                            {content.contentType.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: 12, fontSize: 14, maxWidth: 300 }}>
                          <div 
                            style={{ 
                              whiteSpace: "nowrap", 
                              overflow: "hidden", 
                              textOverflow: "ellipsis"
                            }}
                            title={content.prompt}
                          >
                            {content.prompt}
                          </div>
                        </td>
                        <td style={{ padding: 12 }}>
                          <span style={{
                            padding: "4px 8px",
                            borderRadius: 12,
                            fontSize: 11,
                            fontWeight: 600,
                            background: getStatusColor(content.status) + "20",
                            color: getStatusColor(content.status),
                          }}>
                            {content.status}
                          </span>
                        </td>
                        <td style={{ padding: 12, fontSize: 12, color: "#666" }}>
                          {formatDate(content.createdAt)}
                        </td>
                        <td style={{ padding: 12 }}>
                          {content.status === "completed" && content.downloadUrl && (
                            <button
                              onClick={() => downloadContent(content.contentId)}
                              style={{
                                padding: "6px 12px",
                                background: "#28a745",
                                color: "white",
                                border: "none",
                                borderRadius: 4,
                                cursor: "pointer",
                                fontSize: 12,
                                fontWeight: 600,
                              }}
                            >
                              Download
                            </button>
                          )}
                          {content.status === "failed" && content.error && (
                            <div style={{ fontSize: 11, color: "#dc3545" }}>
                              {content.error}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
