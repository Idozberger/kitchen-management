# scheduler.py
"""
Scheduler for running predictive consumption checks - PostgreSQL VERSION
Runs daily to auto-deplete items based on predictions.
CONVERTED from MongoDB to PostgreSQL
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from utils.consumption_predictor import ConsumptionPredictor


class ConsumptionScheduler:
    """
    Manages scheduled jobs for consumption prediction.
    PostgreSQL version - uses ConsumptionPredictor with proper session management.
    """
    
    def __init__(self):
        """
        Initialize scheduler.
        Note: No db parameter needed - ConsumptionPredictor manages its own sessions
        """
        self.predictor = ConsumptionPredictor()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        print("✅ Scheduler initialized")
    
    
    def start_daily_checks(self, hour=2, minute=0):
        """
        Start daily consumption checks at specified time.
        
        Args:
            hour (int): Hour to run (0-23, default 2 AM)
            minute (int): Minute to run (0-59, default 0)
        """
        # Remove existing job if any
        existing_jobs = self.scheduler.get_jobs()
        for job in existing_jobs:
            if job.id == 'daily_consumption_check':
                self.scheduler.remove_job('daily_consumption_check')
        
        # Add new job with cron trigger
        self.scheduler.add_job(
            func=self._run_consumption_check,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_consumption_check',
            name='Daily Consumption Prediction Check',
            replace_existing=True
        )
        
        print(f"✅ Scheduled daily consumption check at {hour:02d}:{minute:02d}")
    
    
    def run_check_now(self):
        """
        Manually trigger consumption check immediately.
        Useful for testing.
        
        Returns:
            dict: Summary of actions taken
        """
        print("\n🔧 Manual consumption check triggered")
        return self._run_consumption_check()
    
    
    def _run_consumption_check(self):
        """
        Internal method to run the consumption check.
        
        Returns:
            dict: Summary of actions taken
        """
        try:
            print(f"\n{'='*60}")
            print(f"⏰ Scheduled consumption check started at {datetime.now()}")
            print(f"{'='*60}")
            
            summary = self.predictor.check_and_deplete_items()
            
            print(f"\n✅ Consumption check completed successfully")
            return summary
            
        except Exception as e:
            print(f"\n❌ Error in scheduled consumption check: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    
    def stop(self):
        """
        Stop the scheduler.
        """
        self.scheduler.shutdown()
        print("🛑 Scheduler stopped")
    
    
    def get_scheduled_jobs(self):
        """
        Get list of scheduled jobs.
        
        Returns:
            list: List of job information
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
            })
        return jobs


# Export for easy import
__all__ = ['ConsumptionScheduler']