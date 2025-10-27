# backend/app/conversation_manager.py
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from .models import Conversation, AnalyticsMetrics, HistoryRequest

# In-memory conversation storage (in production, use database)
_conversations: List[Conversation] = []

def _parse_timestamp(timestamp) -> datetime:
    """Parse timestamp whether it's a string or datetime object."""
    if isinstance(timestamp, str):
        try:
            # Handle ISO format strings
            if 'T' in timestamp:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                # Handle date-only strings
                return datetime.fromisoformat(timestamp)
        except ValueError:
            # Fallback to current time if parsing fails
            return datetime.now()
    elif isinstance(timestamp, datetime):
        return timestamp
    else:
        # Fallback to current time
        return datetime.now()

def add_conversation(conversation: Conversation) -> None:
    """Add a new conversation to the history."""
    _conversations.append(conversation)

def get_conversations(filters: HistoryRequest) -> Tuple[List[Conversation], int]:
    """Get conversations with filtering and pagination."""
    filtered_conversations = _conversations.copy()
    
    # Apply filters
    if filters.sessionId:
        filtered_conversations = [c for c in filtered_conversations if c.sessionId == filters.sessionId]
    
    if filters.userId:
        filtered_conversations = [c for c in filtered_conversations if c.userId == filters.userId]
    
    if filters.subjectId:
        filtered_conversations = [c for c in filtered_conversations if c.subjectId == filters.subjectId]
    
    if filters.topicId:
        filtered_conversations = [c for c in filtered_conversations if c.topicId == filters.topicId]
    
    if filters.docName:
        filtered_conversations = [c for c in filtered_conversations if c.docName == filters.docName]
    
    if filters.start_date:
        filtered_conversations = [c for c in filtered_conversations if c.timestamp >= filters.start_date]
    
    if filters.end_date:
        filtered_conversations = [c for c in filtered_conversations if c.timestamp <= filters.end_date]
    
    # Sort by timestamp (newest first)
    filtered_conversations.sort(key=lambda x: x.timestamp, reverse=True)
    
    total_count = len(filtered_conversations)
    
    # Apply pagination
    start_idx = filters.offset
    end_idx = start_idx + filters.limit
    paginated_conversations = filtered_conversations[start_idx:end_idx]
    
    return paginated_conversations, total_count

def get_conversation_by_path(sessionId: str, subjectId: str = None, topicId: str = None, docName: str = None) -> List[Conversation]:
    """Get conversations by hierarchical path: sessionId/subjectId/topicId/docName"""
    filtered_conversations = [c for c in _conversations if c.sessionId == sessionId]
    
    if subjectId:
        filtered_conversations = [c for c in filtered_conversations if c.subjectId == subjectId]
    
    if topicId:
        filtered_conversations = [c for c in filtered_conversations if c.topicId == topicId]
    
    if docName:
        filtered_conversations = [c for c in filtered_conversations if c.docName == docName]
    
    return sorted(filtered_conversations, key=lambda x: x.timestamp)

def get_analytics_metrics(start_date: datetime = None, end_date: datetime = None, 
                         subjectId: str = None, topicId: str = None, userId: str = None) -> AnalyticsMetrics:
    """Generate analytics metrics from conversation data."""
    # Filter conversations
    filtered_conversations = _conversations.copy()
    
    if start_date:
        filtered_conversations = [c for c in filtered_conversations if _parse_timestamp(c.timestamp) >= start_date]
    
    if end_date:
        filtered_conversations = [c for c in filtered_conversations if _parse_timestamp(c.timestamp) <= end_date]
    
    if subjectId:
        filtered_conversations = [c for c in filtered_conversations if c.subjectId == subjectId]
    
    if topicId:
        filtered_conversations = [c for c in filtered_conversations if c.topicId == topicId]
    
    if userId:
        filtered_conversations = [c for c in filtered_conversations if c.userId == userId]
    
    if not filtered_conversations:
        return AnalyticsMetrics(
            total_conversations=0,
            total_users=0,
            total_sessions=0,
            average_response_time=0.0,
            total_tokens_used=0,
            mode_usage={},
            subject_usage={},
            topic_usage={},
            document_usage={},
            daily_activity=[],
            hourly_activity=[]
        )
    
    # Calculate metrics
    total_conversations = len(filtered_conversations)
    unique_users = len(set(c.userId for c in filtered_conversations))
    unique_sessions = len(set(c.sessionId for c in filtered_conversations))
    
    # Response time metrics
    response_times = [c.responseTime for c in filtered_conversations if c.responseTime is not None]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
    
    # Token usage
    total_tokens = sum(c.tokenCount for c in filtered_conversations if c.tokenCount is not None)
    
    # Mode usage
    mode_usage = Counter(c.mode for c in filtered_conversations)
    
    # Subject usage
    subject_usage = Counter(c.subjectId for c in filtered_conversations if c.subjectId)
    
    # Topic usage
    topic_usage = Counter(c.topicId for c in filtered_conversations if c.topicId)
    
    # Document usage
    document_usage = Counter(c.docName for c in filtered_conversations if c.docName)
    
    # Daily activity
    daily_activity = defaultdict(int)
    for conv in filtered_conversations:
        timestamp = _parse_timestamp(conv.timestamp)
        date_str = timestamp.strftime("%Y-%m-%d")
        daily_activity[date_str] += 1
    
    daily_activity_list = [{"date": date, "count": count} for date, count in sorted(daily_activity.items())]
    
    # Hourly activity
    hourly_activity = defaultdict(int)
    for conv in filtered_conversations:
        timestamp = _parse_timestamp(conv.timestamp)
        hour = timestamp.hour
        hourly_activity[hour] += 1
    
    hourly_activity_list = [{"hour": hour, "count": count} for hour, count in sorted(hourly_activity.items())]
    
    return AnalyticsMetrics(
        total_conversations=total_conversations,
        total_users=unique_users,
        total_sessions=unique_sessions,
        average_response_time=avg_response_time,
        total_tokens_used=total_tokens,
        mode_usage=dict(mode_usage),
        subject_usage=dict(subject_usage),
        topic_usage=dict(topic_usage),
        document_usage=dict(document_usage),
        daily_activity=daily_activity_list,
        hourly_activity=hourly_activity_list
    )

def get_enhanced_analytics(start_date: datetime = None, end_date: datetime = None, 
                         subjectId: str = None, topicId: str = None, userId: str = None):
    """Generate enhanced analytics matching the new API specification."""
    from .models import TokenUsage, UserEngagement, TopSubject, SystemPerformance, EnhancedAnalyticsResponse
    
    # Filter conversations
    filtered_conversations = _conversations.copy()
    
    if start_date:
        filtered_conversations = [c for c in filtered_conversations if _parse_timestamp(c.timestamp) >= start_date]
    
    if end_date:
        filtered_conversations = [c for c in filtered_conversations if _parse_timestamp(c.timestamp) <= end_date]
    
    if subjectId:
        filtered_conversations = [c for c in filtered_conversations if c.subjectId == subjectId]
    
    if topicId:
        filtered_conversations = [c for c in filtered_conversations if c.topicId == topicId]
    
    if userId:
        filtered_conversations = [c for c in filtered_conversations if c.userId == userId]
    
    if not filtered_conversations:
        return EnhancedAnalyticsResponse(
            period={"fromDate": None, "toDate": None},
            tokenUsage=TokenUsage(internalMode=0, externalMode=0, totalCost=0.0),
            userEngagement=UserEngagement(totalQueries=0, avgSessionDuration=0.0, messagesPerSession=0.0, activeUsers=0),
            topSubjects=[],
            systemPerformance=SystemPerformance(avgResponseTime=0.0, successRate=0.0, uptime=0.0)
        )
    
    # Token Usage Analysis
    internal_tokens = sum(c.tokenCount for c in filtered_conversations if c.mode == "internal" and c.tokenCount)
    external_tokens = sum(c.tokenCount for c in filtered_conversations if c.mode == "cloud" and c.tokenCount)
    
    # Estimate cost (rough calculation: $0.002 per 1K tokens)
    total_tokens = internal_tokens + external_tokens
    total_cost = (total_tokens / 1000) * 0.002
    
    token_usage = TokenUsage(
        internalMode=internal_tokens,
        externalMode=external_tokens,
        totalCost=round(total_cost, 2)
    )
    
    # User Engagement Analysis
    total_queries = len(filtered_conversations)
    unique_users = len(set(c.userId for c in filtered_conversations))
    unique_sessions = len(set(c.sessionId for c in filtered_conversations))
    
    # Calculate average session duration (simplified)
    session_durations = []
    session_groups = defaultdict(list)
    for conv in filtered_conversations:
        session_groups[conv.sessionId].append(conv)
    
    for session_convs in session_groups.values():
        if len(session_convs) > 1:
            timestamps = [_parse_timestamp(conv.timestamp) for conv in session_convs]
            duration = (max(timestamps) - min(timestamps)).total_seconds() / 60  # minutes
            session_durations.append(duration)
    
    avg_session_duration = sum(session_durations) / len(session_durations) if session_durations else 0.0
    messages_per_session = total_queries / unique_sessions if unique_sessions > 0 else 0.0
    
    user_engagement = UserEngagement(
        totalQueries=total_queries,
        avgSessionDuration=round(avg_session_duration, 1),
        messagesPerSession=round(messages_per_session, 1),
        activeUsers=unique_users
    )
    
    # Top Subjects Analysis
    subject_counts = Counter(c.subjectId for c in filtered_conversations if c.subjectId)
    total_subject_queries = sum(subject_counts.values())
    
    top_subjects = []
    for subject_id, count in subject_counts.most_common(5):
        percentage = (count / total_subject_queries * 100) if total_subject_queries > 0 else 0
        top_subjects.append(TopSubject(
            subjectId=subject_id,
            queryCount=count,
            percentage=round(percentage, 1)
        ))
    
    # System Performance Analysis
    response_times = [c.responseTime for c in filtered_conversations if c.responseTime is not None]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
    
    # Calculate success rate (simplified - assume all completed queries are successful)
    success_rate = 98.5  # Placeholder - would need error tracking
    uptime = 99.7  # Placeholder - would need system monitoring
    
    system_performance = SystemPerformance(
        avgResponseTime=round(avg_response_time, 1),
        successRate=success_rate,
        uptime=uptime
    )
    
    # Period information
    if filtered_conversations:
        timestamps = [_parse_timestamp(c.timestamp) for c in filtered_conversations]
        period = {
            "fromDate": min(timestamps).strftime("%Y-%m-%d"),
            "toDate": max(timestamps).strftime("%Y-%m-%d")
        }
    else:
        period = {"fromDate": None, "toDate": None}
    
    return EnhancedAnalyticsResponse(
        period=period,
        tokenUsage=token_usage,
        userEngagement=user_engagement,
        topSubjects=top_subjects,
        systemPerformance=system_performance
    )

def get_all_conversations() -> List[Conversation]:
    """Get all conversations (for debugging/admin purposes)."""
    return _conversations.copy()

def clear_conversations() -> None:
    """Clear all conversation history."""
    global _conversations
    _conversations = []

def get_conversation_stats() -> dict:
    """Get basic conversation statistics."""
    return {
        "total_conversations": len(_conversations),
        "unique_users": len(set(c.userId for c in _conversations)),
        "unique_sessions": len(set(c.sessionId for c in _conversations)),
        "date_range": {
            "earliest": min(c.timestamp for c in _conversations) if _conversations else None,
            "latest": max(c.timestamp for c in _conversations) if _conversations else None
        }
    }
