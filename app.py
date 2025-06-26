from flask import Flask, jsonify
from flask_cors import CORS
from flask_restful import Api
from extensions import db, socketio, scheduler
from resourses import * 
from services import * 
from scheduler import * 
import signal
import sys
import urllib.parse
import os
import logging


# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})
    
    db_url = os.environ.get('DATABASE_URL')
    
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    else:
        connection_string = os.environ.get('DB_CONNECTION_STRING', 
            "Driver={ODBC Driver 17 for SQL Server};"
            "Server=db15097.public.databaseasp.net;"
            "Database=db15097;"
            "UID=db15097;"
            "PWD=f!2F@6PnjQ-9;"
            "Encrypt=no;"
            "TrustServerCertificate=yes;"
            "MultipleActiveResultSets=True;"
            "Connection Timeout=30;"
        )
        params = urllib.parse.quote_plus(connection_string)
        app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc:///?odbc_connect={params}"
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    @app.route('/health')
    def health_check():
        return jsonify({'status': 'healthy'}), 200
    
    app.config['JSON_AS_ASCII'] = False
    
    app.config['SCHEDULER_API_ENABLED'] = False
    app.config['SCHEDULER_TIMEZONE'] = 'UTC'
    app.config['SCHEDULER_DAEMON'] = False  
       
    db.init_app(app)
    
   
    
    socketio.init_app(app, 
                     cors_allowed_origins="*",
                     async_mode='threading',  
                     daemon=False)  
    scheduler.init_app(app)
    
    api = Api(app)
    
  
    
    # Enrollment Period
    api.add_resource(EnrollmentPeriodResource, '/api/enrollment-periods')
    api.add_resource(CurrentEnrollmentPeriodResource, '/api/enrollment-periods/current')

    # Course Recommendation  
    api.add_resource(SmartRecommendationsResource,'/api/recommendations/smart/<int:student_id>')
    api.add_resource(MandatoryCoursesRecommendationResource,'/api/recommendations/mandatory/<int:student_id>')
    api.add_resource(ElectiveCoursesRecommendationResource,'/api/recommendations/elective/<int:student_id>')
    api.add_resource(FailedCoursesRetryRecommendationResource,'/api/recommendations/failed-retry/<int:student_id>')
    api.add_resource(GPAImprovementRecommendationResource,'/api/recommendations/gpa-improvement/<int:student_id>')
    api.add_resource(MissedMandatoryCoursesResource,'/api/recommendations/missed-mandatory-courses/<int:student_id>')
    api.add_resource(FutureMandatoryCoursesResource,'/api/recommendations/future-mandatory-courses/<int:student_id>')

    # Course Enrollment
    api.add_resource(CourseEnrollmentResource, '/api/students/enrollments/<int:student_id>')
    api.add_resource(CourseEnrollmentCancellationResource, '/api/students/enrollments/cancel/<int:student_id>')
    api.add_resource(CourseEnrollmentHardDeleteResource, '/api/enrollments/hard-delete/<int:enrollment_id>')
    api.add_resource(StudentEnrollmentStatusResource, '/api/students/enrollment-status/<int:student_id>')

    # Graduation Eligibility
    api.add_resource(GraduationEligibilityResource, '/api/students/graduation-eligibility/<int:student_id>')
    api.add_resource(GraduationSummaryResource, '/api/students/graduation-summary/<int:student_id>')

    # Academic Warning
    api.add_resource(AcademicWarningResource, '/api/academic-warnings', '/api/academic-warnings/<int:student_id>')
    api.add_resource(ResolveWarningResource, '/api/academic-warnings/<int:warning_id>/resolve')
    api.add_resource(WarningStatsResource, '/api/academic-warnings/stats')
    api.add_resource(StudentWarningCheckResource, '/api/academic-warnings/check/<int:student_id>')
    api.add_resource(StudentWarningResolveResource, '/api/academic-warnings/resolve/<int:student_id>')




    # Academic Status Analysis
    api.add_resource(AcademicStatusAnalysisResource, '/api/academic-status-analysis/<int:student_id>')
    api.add_resource(StudentBasicInfoResource, '/api/academic-status/basic-info/<int:student_id>')
    api.add_resource(GPAAnalysisResource, '/api/academic-status/gpa-analysis/<int:student_id>')
    api.add_resource(PerformancePatternsResource, '/api/academic-status/performance-patterns/<int:student_id>')
    api.add_resource(RiskAssessmentResource, '/api/academic-status/risk-assessment/<int:student_id>')
    api.add_resource(CourseAnalysisResource, '/api/academic-status/course-analysis/<int:student_id>')
    api.add_resource(AttendanceAnalysisResource, '/api/academic-status/attendance-analysis/<int:student_id>')
    api.add_resource(AcademicWarningsSummaryResource, '/api/academic-status/warnings-summary/<int:student_id>')
    api.add_resource(PeerComparisonResource, '/api/academic-status/peer-comparison/<int:student_id>')
    api.add_resource(PredictionsResource, '/api/academic-status/predictions/<int:student_id>')
    api.add_resource(InterventionsResource, '/api/academic-status/interventions/<int:student_id>')
    api.add_resource(AIInsightsResource, '/api/academic-status/ai-insights/<int:student_id>')

    # Academic Path Planning - التخطيط الأكاديمي المطور
    api.add_resource(AcademicPathPlanningResource, '/api/academic-path-planning/<int:student_id>')
    api.add_resource(DivisionRecommendationResource, '/api/division-recommendations/<int:student_id>')
    api.add_resource(CourseScheduleResource, '/api/course-schedule/<int:student_id>')
    api.add_resource(StudentPerformanceAnalysisResource, '/api/student-performance-analysis/<int:student_id>')

    # إعداد مجدول الإنذارات الأكاديمية
    warning_scheduler = AcademicWarningScheduler(scheduler)
    warning_scheduler.setup_jobs()








    
    logger.info("تم إنشاء التطبيق بنجاح")
    return app  

app = create_app()

def cleanup_resources():
    with app.app_context():
        try:
            scheduler.shutdown()
            db.session.remove()
            db.engine.dispose()
            logger.info("cleaned up")
        except Exception as e:
            logger.error(f'Error during cleanup: {str(e)}')
    
def signal_handler(sig, frame):
    logger.info('تم استلام إشارة إنهاء. جاري إغلاق التطبيق...')
    cleanup_resources()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"بدء تشغيل نظام شؤون الطلاب على المنفذ {port}")
    
    with app.app_context():
        try:
            db.create_all()
            logger.info("تم إنشاء جداول قاعدة البيانات بنجاح")
        except Exception as e:
            logger.error(f"خطأ في إنشاء جداول قاعدة البيانات: {str(e)}")
    
    scheduler.start()
    try:
        socketio.run(app, debug=False, use_reloader=False, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        logger.info('تم إيقاف التطبيق بواسطة المستخدم')
    except Exception as e:
        logger.error(f'حدث خطأ أثناء تشغيل التطبيق: {str(e)}')
    finally:
        cleanup_resources()

