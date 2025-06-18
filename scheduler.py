from datetime import datetime, timedelta
from services import AcademicWarningService
import logging

logger = logging.getLogger(__name__)

class AcademicWarningScheduler:
    
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.warning_service = AcademicWarningService()
    
    def setup_jobs(self):
        """إعداد المهام المجدولة للإنذارات الأكاديمية"""
        try:
            # تشغيل يومي في الساعة 2 صباحاً
            self.scheduler.add_job(
                func=self.daily_warning_check,
                trigger="cron",
                hour=2,
                minute=0,
                id='daily_academic_warning_check',
                replace_existing=True
            )
            
            # تشغيل أسبوعي يوم الأحد في الساعة 1 صباحاً
            self.scheduler.add_job(
                func=self.weekly_warning_check,
                trigger="cron",
                day_of_week=6,  # Sunday
                hour=1,
                minute=0,
                id='weekly_academic_warning_check',
                replace_existing=True
            )
            
            logger.info("تم إعداد مهام الإنذارات الأكاديمية المجدولة")
            
        except Exception as e:
            logger.error(f"خطأ في إعداد مهام الإنذارات المجدولة: {str(e)}")
    
    def daily_warning_check(self):
        """فحص يومي للإنذارات"""
        try:
            current_semester = self.warning_service.get_current_semester()
            warnings_count = self.warning_service.check_all_students_warnings(current_semester)
            logger.info(f"الفحص اليومي للإنذارات: تم إصدار {warnings_count} إنذار")
        except Exception as e:
            logger.error(f"خطأ في الفحص اليومي للإنذارات: {str(e)}")
    
    def weekly_warning_check(self):
        """فحص أسبوعي شامل"""
        try:
            current_semester = self.warning_service.get_current_semester()
            warnings_count = self.warning_service.check_all_students_warnings(current_semester)
            logger.info(f"الفحص الأسبوعي للإنذارات: تم إصدار {warnings_count} إنذار")
        except Exception as e:
            logger.error(f"خطأ في الفحص الأسبوعي للإنذارات: {str(e)}")
    
    def manual_check(self, semester=None):
        """فحص يدوي للإنذارات"""
        try:
            if not semester:
                semester = self.warning_service.get_current_semester()
            
            warnings_count = self.warning_service.check_all_students_warnings(semester)
            logger.info(f"الفحص اليدوي للإنذارات: تم إصدار {warnings_count} إنذار")
            return warnings_count
        except Exception as e:
            logger.error(f"خطأ في الفحص اليدوي للإنذارات: {str(e)}")
            return 0 
