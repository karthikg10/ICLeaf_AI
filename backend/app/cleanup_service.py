# backend/app/cleanup_service.py
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class CleanupService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.content_dir = Path("./data/content")
        self.retention_days = 30  # Keep files for 30 days as per spec
        
    def start(self):
        """Start the cleanup scheduler."""
        # Schedule daily cleanup at 2 AM
        self.scheduler.add_job(
            self.cleanup_old_files,
            CronTrigger(hour=2, minute=0),
            id='daily_cleanup',
            name='Daily cleanup of old files',
            replace_existing=True
        )
        self.scheduler.start()
        print("[cleanup] Daily cleanup job scheduled for 2:00 AM")
    
    def stop(self):
        """Stop the cleanup scheduler."""
        self.scheduler.shutdown()
        print("[cleanup] Cleanup scheduler stopped")
    
    async def cleanup_old_files(self):
        """Clean up files older than retention_days."""
        try:
            if not self.content_dir.exists():
                print("[cleanup] Content directory does not exist, skipping cleanup")
                return
            
            cutoff_time = time.time() - (self.retention_days * 24 * 60 * 60)
            deleted_count = 0
            total_size_freed = 0
            
            # Walk through all user directories
            for user_dir in self.content_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                    
                # Walk through content directories
                for content_dir in user_dir.iterdir():
                    if not content_dir.is_dir():
                        continue
                    
                    # Check if directory is older than retention period
                    if content_dir.stat().st_mtime < cutoff_time:
                        try:
                            # Calculate size before deletion
                            dir_size = sum(f.stat().st_size for f in content_dir.rglob('*') if f.is_file())
                            
                            # Remove the entire content directory
                            import shutil
                            shutil.rmtree(content_dir)
                            
                            deleted_count += 1
                            total_size_freed += dir_size
                            
                            print(f"[cleanup] Deleted old content: {content_dir}")
                            
                        except Exception as e:
                            print(f"[cleanup] Error deleting {content_dir}: {e}")
            
            if deleted_count > 0:
                size_mb = total_size_freed / (1024 * 1024)
                print(f"[cleanup] Cleanup completed: {deleted_count} directories deleted, {size_mb:.2f} MB freed")
            else:
                print("[cleanup] No old files found for cleanup")
                
        except Exception as e:
            print(f"[cleanup] Error during cleanup: {e}")
    
    async def cleanup_now(self):
        """Manually trigger cleanup (for testing)."""
        print("[cleanup] Manual cleanup triggered")
        await self.cleanup_old_files()

# Global cleanup service instance
cleanup_service = CleanupService()

