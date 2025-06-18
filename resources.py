from datetime import datetime
from flask import request, jsonify
from flask_restful import Resource
from sqlalchemy import func
import logging

# Import services
from services import (
    AcademicPathService, 
    DivisionRecommendationService, 
    VerySmartAcademicPathPlanningService,
    AcademicStatusAnalysisService,
    AcademicWarningService,
    CourseEnrollmentService,
    EnrollmentPeriodService,
    GraduationEligibilityService,
    SmartCourseRecommendationService
)

# Import models
from models import AcademicWarnings, Students
from extensions import db

# Configure logging
logger = logging.getLogger(__name__)

class GraduationEligibilityResource(Resource):
    """API للحصول على تقرير أهلية التخرج الشامل"""
    
    def get(self, student_id):
        """
        الحصول على تقرير أهلية التخرج الشامل للطالب
        """
        try:
            # التحقق من صحة معرف الطالب
            if not student_id or student_id <= 0:
                return {
                    "success": False,
                    "message": "معرف الطالب غير صحيح",
                    "error": "INVALID_STUDENT_ID"
                }, 400
            
            # الحصول على تقرير أهلية التخرج
            result = GraduationEligibilityService.get_graduation_eligibility(student_id)
            
            if result["success"]:
                return result, 200
            else:
                return result, 404 if "STUDENT_NOT_FOUND" in result.get("error", "") else 500
                
        except Exception as e:
            logger.error(f"Error in GraduationEligibilityResource.get: {str(e)}")
            return {
                "success": False,
                "message": "حدث خطأ أثناء الحصول على تقرير أهلية التخرج",
                "error": str(e)
            }, 500

class GraduationSummaryResource(Resource):
    """API للحصول على ملخص سريع لحالة التخرج"""
    
    def get(self, student_id):
        """
        الحصول على ملخص سريع لحالة التخرج
        """
        try:
            # التحقق من صحة معرف الطالب
            if not student_id or student_id <= 0:
                return {
                    "success": False,
                    "message": "معرف الطالب غير صحيح",
                    "error": "INVALID_STUDENT_ID"
                }, 400
            
            # الحصول على التقرير الكامل
            full_result = GraduationEligibilityService.get_graduation_eligibility(student_id)
            
            if not full_result["success"]:
                return full_result, 404 if "STUDENT_NOT_FOUND" in full_result.get("error", "") else 500
            
            # إنشاء الملخص السريع
            summary = {
                "success": True,
                "message": "تم الحصول على ملخص حالة التخرج بنجاح",
                "student_info": {
                    "name": full_result["student_info"]["name"],
                    "division": full_result["student_info"]["division"],
                    "academic_year": full_result["student_info"]["academic_year"]
                },
                "graduation_status": full_result["graduation_status"],
                "completion_summary": {
                    "total_credits": {
                        "completed": full_result["credits_analysis"]["completed_total"],
                        "required": full_result["credits_analysis"]["total_required"],
                        "remaining": full_result["credits_analysis"]["remaining_total"]
                    },
                    "gpa": {
                        "current": full_result["gpa_analysis"]["current_gpa"],
                        "required": full_result["gpa_analysis"]["minimum_required"],
                        "status": full_result["gpa_analysis"]["status"]
                    }
                },
                "quick_stats": {
                    "completed_courses": len(full_result["completed_courses"]),
                    "remaining_courses": len(full_result["remaining_courses"]),
                    "failed_courses": len(full_result["failed_courses"]),
                    "active_warnings": len([w for w in full_result["academic_warnings"] if w.get("is_active", False)])
                },
                "top_recommendations": full_result["recommendations"][:3],  # أهم 3 توصيات
                "generated_at": full_result["generated_at"]
            }
            
            return summary, 200
                
        except Exception as e:
            logger.error(f"Error in GraduationSummaryResource.get: {str(e)}")
            return {
                "success": False,
                "message": "حدث خطأ أثناء الحصول على ملخص حالة التخرج",
                "error": str(e)
            }, 500

class EnrollmentPeriodResource(Resource):
    
    def post(self):
        try:
            data = request.get_json()
            
            if not data:
                return {
                    "status": "فشل",
                    "message": "لم يتم إرسال بيانات في الطلب"
                }, 400
            
            semester = data.get('Semester')
            start_date_str = data.get('StartDate')
            end_date_str = data.get('EndDate')
            
            if not semester:
                return {
                    "status": "فشل",
                    "message": "الفصل الدراسي مطلوب"
                }, 400
            
            if not start_date_str:
                return {
                    "status": "فشل",
                    "message": "تاريخ بداية التسجيل مطلوب"
                }, 400
            
            if not end_date_str:
                return {
                    "status": "فشل",
                    "message": "تاريخ نهاية التسجيل مطلوب"
                }, 400
            
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError as e:
                return {
                    "status": "فشل",
                    "message": f"تنسيق التاريخ غير صحيح. يجب أن يكون بتنسيق ISO 8601: {str(e)}"
                }, 400
            
            result = EnrollmentPeriodService.create_enrollment_period(
                semester, start_date, end_date
            )
            
            if result["success"]:
                return {
                    "status": "نجاح",
                    "message": result["message"],
                    "data": result["data"]
                }, 201
            else:
                return {
                    "status": "فشل",
                    "message": result["message"],
                    "errors": result.get("errors", [])
                }, 400
                
        except Exception as e:
            return {
                "status": "فشل",
                "message": f"حدث خطأ أثناء معالجة الطلب: {str(e)}"
            }, 500
    
    def get(self):
        try:
            result = EnrollmentPeriodService.get_all_enrollment_periods()
            
            if result["success"]:
                return {
                    "status": "نجاح",
                    "message": result["message"],
                    "data": result["data"]
                }, 200
            else:
                return {
                    "status": "فشل",
                    "message": result["message"]
                }, 500
                
        except Exception as e:
            return {
                "status": "فشل",
                "message": f"حدث خطأ أثناء استرجاع فترات التسجيل: {str(e)}"
            }, 500

class CurrentEnrollmentPeriodResource(Resource):
    
    def get(self):
        try:
            result = EnrollmentPeriodService.get_current_enrollment_period()
            
            if result["success"]:
                return {
                    "status": "نجاح",
                    "message": result["message"],
                    "data": result["data"]
                }, 200
            else:
                return {
                    "status": "فشل",
                    "message": result["message"]
                }, 404
                
        except Exception as e:
            return {
                "status": "فشل",
                "message": f"حدث خطأ أثناء البحث عن فترة التسجيل الحالية: {str(e)}"
            }, 500

class SmartRecommendationsResource(Resource):
    
    def __init__(self):
        self.service = SmartCourseRecommendationService()
    
    def get(self, student_id):
        try:
            logger.info(f"Getting smart recommendations for student {student_id}")
            
            recommendations = self.service.get_smart_recommendations(student_id)
            
            if isinstance(recommendations, tuple):
                error_data, status_code = recommendations
                return {
                    
                    'data': None
                }, status_code
            
            return {
                
                'data': recommendations
            }, 200
            
        except Exception as e:
            logger.error(f"Error in SmartRecommendationsResource: {str(e)}")
            return {
                
                'data': None
            }, 500

class MandatoryCoursesRecommendationResource(Resource):
    
    def __init__(self):
        self.service = SmartCourseRecommendationService()
    
    def get(self, student_id):
        try:
            logger.info(f"Getting mandatory course recommendations for student {student_id}")
            
            recommendations = self.service.get_smart_recommendations(student_id)
            
            if isinstance(recommendations, tuple):
                error_data, status_code = recommendations
                return {
                    
                    'data': None
                }, status_code
            
            mandatory_courses = recommendations.get('mandatory_courses', [])
            
            for course_rec in mandatory_courses:
                original_course = course_rec.get('course', {})
                
                clean_course = {
                    'id': original_course.get('id'),
                    'name': original_course.get('name'),
                    'code': original_course.get('code'),
                    'description': original_course.get('description'),
                    'credits': original_course.get('credits'),
                    'available_seats': original_course.get('max_seats', 100) - original_course.get('current_enrolled', 0),
                    'professor_name': original_course.get('professor_name'),
                    'day_name': original_course.get('day_name'),
                    'start_time': original_course.get('start_time'),
                    'end_time': original_course.get('end_time'),
                    'location': original_course.get('location')
                }
                
                course_rec['course'] = clean_course
                
                course_rec['priority_score'] = round(course_rec.get('priority_score', 0), 2)
                course_rec['difficulty_score'] = round(course_rec.get('difficulty_score', 0), 2)
            
            return {
               
                'data': {
                    'mandatory_courses': mandatory_courses,
                    'count': len(mandatory_courses)
                }
            }, 200
            
        except Exception as e:
            logger.error(f"Error in MandatoryCoursesRecommendationResource: {str(e)}")
            return {
                
                'data': None
            }, 500

class ElectiveCoursesRecommendationResource(Resource):
    
    def __init__(self):
        self.service = SmartCourseRecommendationService()
    
    def get(self, student_id):
        try:
            logger.info(f"Getting elective course recommendations for student {student_id}")
            
            recommendations = self.service.get_smart_recommendations(student_id)
            
            if isinstance(recommendations, tuple):
                error_data, status_code = recommendations
                return {
                    
                    'data': None
                }, status_code
            
            elective_courses = recommendations.get('elective_courses', [])
            
            for course_rec in elective_courses:
                original_course = course_rec.get('course', {})
                
                clean_course = {
                    'id': original_course.get('id'),
                    'name': original_course.get('name'),
                    'code': original_course.get('code'),
                    'description': original_course.get('description'),
                    'credits': original_course.get('credits'),
                    'available_seats': original_course.get('max_seats', 100) - original_course.get('current_enrolled', 0),
                    'professor_name': original_course.get('professor_name'),
                    'day_name': original_course.get('day_name'),
                    'start_time': original_course.get('start_time'),
                    'end_time': original_course.get('end_time'),
                    'location': original_course.get('location')
                }
                
                clean_recommendation = {
                    'course': clean_course,
                    'recommendation_reason': course_rec.get('recommendation_reason')
                }
                
                elective_courses[elective_courses.index(course_rec)] = clean_recommendation
            
            return {
                
                'data': {
                    'elective_courses': elective_courses,
                    'count': len(elective_courses)
                }
            }, 200
            
        except Exception as e:
            logger.error(f"Error in ElectiveCoursesRecommendationResource: {str(e)}")
            return {
                
                'data': None
            }, 500

class FailedCoursesRetryRecommendationResource(Resource):
    
    def __init__(self):
        self.service = SmartCourseRecommendationService()
    
    def get(self, student_id):
        try:
            logger.info(f"Getting failed courses retry recommendations for student {student_id}")
            
            recommendations = self.service.get_smart_recommendations(student_id)
            
            if isinstance(recommendations, tuple):
                error_data, status_code = recommendations
                return {
                    
                    'data': None
                }, status_code
            
            failed_courses_data = recommendations.get('failed_courses_retry', {})
            
            if isinstance(failed_courses_data, dict):
                # تنظيف بيانات المواد الراسبة
                courses = failed_courses_data.get('courses', [])
                clean_courses = []
                
                for course_rec in courses:
                    original_course = course_rec.get('course', {})
                    
                    # إنشاء نسخة نظيفة من بيانات المادة
                    clean_course = {
                        'id': original_course.get('id'),
                        'name': original_course.get('name'),
                        'code': original_course.get('code'),
                        'description': original_course.get('description'),
                        'credits': original_course.get('credits'),
                        'available_seats': original_course.get('max_seats', 100) - original_course.get('current_enrolled', 0),
                        'professor_name': original_course.get('professor_name'),
                        'day_name': original_course.get('day_name'),
                        'start_time': original_course.get('start_time'),
                        'end_time': original_course.get('end_time'),
                        'location': original_course.get('location')
                    }
                    
                    # إنشاء نسخة نظيفة من التوصية
                    clean_recommendation = {
                        'course': clean_course,
                        'priority_score': round(course_rec.get('priority_score', 0), 2),
                        'difficulty_score': round(course_rec.get('difficulty_score', 0), 2),
                        'recommendation_reason': course_rec.get('recommendation_reason', 'أولوية عالية للتخرج'),
                        'suggested_semester': course_rec.get('suggested_semester', 1)
                    }
                    
                    clean_courses.append(clean_recommendation)
                
                return {
                    
                    'data': {
                        'failed_courses_info': {
                            'message': failed_courses_data.get('message'),
                            'recommendation': failed_courses_data.get('recommendation')
                        },
                        'failed_courses_retry': clean_courses,
                        'count': len(clean_courses)
                    }
                }, 200
            else:
                return {
                    
                    'data': {
                        'failed_courses_retry': failed_courses_data,
                        'count': len(failed_courses_data)
                    }
                }, 200
            
        except Exception as e:
            logger.error(f"Error in FailedCoursesRetryRecommendationResource: {str(e)}")
            return {
               
                'data': None
            }, 500

class GPAImprovementRecommendationResource(Resource):
    
    def __init__(self):
        self.service = SmartCourseRecommendationService()
    
    def get(self, student_id):
        try:
            logger.info(f"Getting GPA improvement recommendations for student {student_id}")
            
            recommendations = self.service.get_smart_recommendations(student_id)
            
            if isinstance(recommendations, tuple):
                error_data, status_code = recommendations
                return {
                    
                    'data': None
                }, status_code
            
            gpa_improvement_data = recommendations.get('gpa_improvement_courses', {})
            
            if isinstance(gpa_improvement_data, dict):
                return {
                    
                    'data': {
                        'gpa_improvement_info': {
                            'message': gpa_improvement_data.get('message'),
                            
                            'recommendation': gpa_improvement_data.get('recommendation')
                        },
                        'gpa_improvement_courses': gpa_improvement_data.get('courses', []),
                        'count': len(gpa_improvement_data.get('courses', []))
                    }
                }, 200
            else:
                return {
                    
                    'data': {
                        'gpa_improvement_courses': gpa_improvement_data,
                        'count': len(gpa_improvement_data)
                    }
                }, 200
            
        except Exception as e:
            logger.error(f"Error in GPAImprovementRecommendationResource: {str(e)}")
            return {
                'success': False,
                'message': 'حدث خطأ أثناء جلب توصيات تحسين المعدل',
                'data': None
            }, 500

class MissedMandatoryCoursesResource(Resource):
    
    def get(self, student_id):
        try:
            service = SmartCourseRecommendationService()
            
            student_data = service._get_enhanced_student_data(student_id)
            if not student_data:
                return {"error": "الطالب غير موجود"}, 404
            
            academic_status = service._classify_student_academic_status(student_data)
            
            available_courses = service._get_available_courses(student_data)
            
            missed_mandatory_courses = []
            current_semester = student_data['current_semester']
            
            for course in available_courses:
                if (course['is_mandatory'] and 
                    course['semester'] < current_semester):
                    
                    # إنشاء نسخة نظيفة من بيانات المادة
                    clean_course = {
                        'id': course.get('id'),
                        'name': course.get('name'),
                        'code': course.get('code'),
                        'description': course.get('description'),
                        'credits': course.get('credits'),
                        'available_seats': course.get('max_seats', 100) - course.get('current_enrolled', 0),
                        'professor_name': course.get('professor_name'),
                        'day_name': course.get('day_name'),
                        'start_time': course.get('start_time'),
                        'end_time': course.get('end_time'),
                        'location': course.get('location')
                    }
                    
                    original_semester = course.get('semester')
                    semesters_delayed = current_semester - original_semester
                    
                    priority_score = service._calculate_mandatory_priority(course, student_data)
                    priority_score += 0.2  
                    
                    difficulty_score = service._estimate_course_difficulty(course, student_data)
                    
                    missed_course_data = {
                        'course': clean_course,
                        'priority_score': min(priority_score, 1.0),
                        'difficulty_score': difficulty_score,
                        'original_semester': original_semester,
                        'semesters_delayed': semesters_delayed,
                        'recommendation_reason': f"مادة إجبارية من الترم {original_semester} - متأخرة {semesters_delayed} ترم - مطلوبة للتخرج"
                    }
                    
                    missed_mandatory_courses.append(missed_course_data)
            
            missed_mandatory_courses.sort(
                key=lambda x: (x['semesters_delayed'], x['priority_score']), 
                reverse=True
            )
            
            return {
                'missed_mandatory_courses': missed_mandatory_courses,
                'total_count': len(missed_mandatory_courses),
                'summary': {
                    'message': f"يوجد {len(missed_mandatory_courses)} مادة إجبارية من ترمات سابقة لم يتم أخذها",
                    'recommendation': "يُنصح بأخذ هذه المواد في أقرب وقت ممكن لأنها مطلوبة للتخرج"
                }
            }
            
        except Exception as e:
            logger.error(f"Error in missed mandatory courses API: {str(e)}")
            return {"error": str(e)}, 500

class FutureMandatoryCoursesResource(Resource):
    
    def get(self, student_id):
        try:
            service = SmartCourseRecommendationService()
            
            student_data = service._get_enhanced_student_data(student_id)
            if not student_data:
                return {"error": "الطالب غير موجود"}, 404
            
            academic_status = service._classify_student_academic_status(student_data)
            
            available_courses = service._get_available_courses(student_data)
            
            future_mandatory_courses = []
            current_semester = student_data['current_semester']
            
            for course in available_courses:
                if (course['is_mandatory'] and 
                    course['semester'] > current_semester):
                    
                    # إنشاء نسخة نظيفة من بيانات المادة
                    clean_course = {
                        'id': course.get('id'),
                        'name': course.get('name'),
                        'code': course.get('code'),
                        'description': course.get('description'),
                        'credits': course.get('credits'),
                        'available_seats': course.get('max_seats', 100) - course.get('current_enrolled', 0),
                        'professor_name': course.get('professor_name'),
                        'day_name': course.get('day_name'),
                        'start_time': course.get('start_time'),
                        'end_time': course.get('end_time'),
                        'location': course.get('location')
                    }
                    
                    original_semester = course.get('semester')
                    semesters_early = original_semester - current_semester
                    
                    readiness_score = service._calculate_student_readiness(course, student_data)
                    difficulty_score = service._estimate_course_difficulty(course, student_data)
                    
                    future_course_data = {
                        'course': clean_course,
                        'difficulty_score': difficulty_score,
                        'original_semester': original_semester,
                        'semesters_early': semesters_early,
                        'recommendation_reason': f"مادة إجبارية من الترم {original_semester} - يمكن أخذها مبكراً",
                        'early_enrollment_benefit': 'تقليل العبء الدراسي في الترمات القادمة' if readiness_score > 0.7 else 'يُنصح بالانتظار حتى الترم المحدد'
                    }
                    
                    future_mandatory_courses.append(future_course_data)
            
            future_mandatory_courses.sort(
                key=lambda x: (-x['semesters_early']), 
                reverse=True
            )
            
            return {
                'future_mandatory_courses': future_mandatory_courses,
                'total_count': len(future_mandatory_courses),
                'summary': {
                    'message': f"يوجد {len(future_mandatory_courses)} مادة إجبارية من ترمات قادمة يمكن أخذها مبكراً",
                    'recommendation': "يُنصح بأخذ المواد التي لديك استعداد عالي لها فقط"
                }
            }
            
        except Exception as e:
            logger.error(f"Error in future mandatory courses API: {str(e)}")
            return {"error": str(e)}, 500


class CourseEnrollmentResource(Resource):
    """API لتسجيل الطلاب في المواد"""
    
    def post(self, student_id):
        """تسجيل طالب في مادة جديدة"""
        try:
            # الحصول على بيانات الطلب
            data = request.get_json()
            
            if not data or 'course_id' not in data:
                return {
                    "success": False,
                    "message": "يجب تحديد معرف المادة (course_id)"
                }, 400
            
            course_id = data['course_id']
            
            # التحقق من صحة معرف المادة
            if not isinstance(course_id, int) or course_id <= 0:
                return {
                    "success": False,
                    "message": "معرف المادة غير صحيح"
                }, 400
            
            # استدعاء خدمة التسجيل
            result = CourseEnrollmentService.enroll_student_in_course(student_id, course_id)
            
            if result["success"]:
                return result, 201
            else:
                return result, 400
                
        except Exception as e:
            logger.error(f"Error in CourseEnrollmentResource.post: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ في الخادم: {str(e)}"
            }, 500
    
    def get(self, student_id):
        """الحصول على جميع تسجيلات الطالب في الفصل الحالي"""
        try:
            result = CourseEnrollmentService.get_student_enrollments(student_id)
            
            if result["success"]:
                return result, 200
            else:
                return result, 404
                
        except Exception as e:
            logger.error(f"Error in CourseEnrollmentResource.get: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ في الخادم: {str(e)}"
            }, 500

class CourseEnrollmentCancellationResource(Resource):
    """API لإلغاء تسجيل المواد (حذف مؤقت)"""
    
    def put(self, student_id):
        """إلغاء تسجيل مادة للطالب"""
        try:
            # الحصول على بيانات الطلب
            data = request.get_json()
            
            if not data or 'enrollment_id' not in data:
                return {
                    "success": False,
                    "message": "يجب تحديد معرف التسجيل (enrollment_id)"
                }, 400
            
            enrollment_id = data['enrollment_id']
            
            # التحقق من صحة معرف التسجيل
            if not isinstance(enrollment_id, int) or enrollment_id <= 0:
                return {
                    "success": False,
                    "message": "معرف التسجيل غير صحيح"
                }, 400
            
            # استدعاء خدمة الإلغاء
            result = CourseEnrollmentService.cancel_enrollment(enrollment_id)
            
            if result["success"]:
                return result, 200
            else:
                return result, 400
                
        except Exception as e:
            logger.error(f"Error in CourseEnrollmentCancellationResource.put: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ في الخادم: {str(e)}"
            }, 500

class CourseEnrollmentHardDeleteResource(Resource):
    """API للحذف النهائي للتسجيلات (للإدارة فقط)"""
    
    def delete(self, enrollment_id):
        """حذف نهائي لتسجيل مادة"""
        try:
            # التحقق من صحة معرف التسجيل
            if not isinstance(enrollment_id, int) or enrollment_id <= 0:
                return {
                    "success": False,
                    "message": "معرف التسجيل غير صحيح"
                }, 400
            
            # استدعاء خدمة الحذف النهائي
            result = CourseEnrollmentService.hard_delete_enrollment(enrollment_id)
            
            if result["success"]:
                return result, 200
            else:
                return result, 404
                
        except Exception as e:
            logger.error(f"Error in CourseEnrollmentHardDeleteResource.delete: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ في الخادم: {str(e)}"
            }, 500

class StudentEnrollmentStatusResource(Resource):
    """API للحصول على حالة تسجيل الطالب وإحصائياته"""
    
    def get(self, student_id):
        """الحصول على حالة تسجيل الطالب مع الإحصائيات"""
        try:
            result = CourseEnrollmentService.get_student_enrollments(student_id)
            
            if result["success"]:
                # إضافة معلومات إضافية عن حالة التسجيل
                data = result["data"]
                
                # حساب إحصائيات إضافية
                enrollment_stats = {
                    "can_enroll_more": data["remaining_credits"] > 0,
                    "enrollment_percentage": (data["total_active_credits"] / data["max_allowed_credits"]) * 100,
                    "total_enrollments": len(data["active_enrollments"]) + len(data["cancelled_enrollments"]),
                    "active_count": len(data["active_enrollments"]),
                    "cancelled_count": len(data["cancelled_enrollments"])
                }
                
                result["data"]["enrollment_stats"] = enrollment_stats
                return result, 200
            else:
                return result, 404
                
        except Exception as e:
            logger.error(f"Error in StudentEnrollmentStatusResource.get: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ في الخادم: {str(e)}"
            }, 500


class AcademicWarningResource(Resource):
    
    def __init__(self):
        self.warning_service = AcademicWarningService()
    
    def get(self, student_id=None):
        """الحصول على الإنذارات الأكاديمية"""
        try:
            if student_id:
                # Get warnings for specific student
                status = request.args.get('status')
                warnings = self.warning_service.get_student_warnings(student_id, status)
                
                # Get student info
                student = Students.query.get(student_id)
                if not student:
                    return {'error': 'الطالب غير موجود'}, 404
                
                return {
                    'student': {
                        'id': student.Id,
                        'name': student.Name,
                        'semester': student.Semester
                    },
                    'warnings': [{
                        'id': w.Id,
                        'type': w.WarningType,
                        'type_ar': self.warning_service.WARNING_TYPES.get(w.WarningType, w.WarningType),
                        'level': w.WarningLevel,
                        'level_ar': self.warning_service.WARNING_LEVELS.get(w.WarningLevel, str(w.WarningLevel)),
                        'description': w.Description,
                        'semester': w.Semester,
                        'issue_date': w.IssueDate.isoformat() if w.IssueDate else None,
                        'resolved_date': w.ResolvedDate.isoformat() if w.ResolvedDate else None,
                        'status': w.Status,
                        'action_required': w.ActionRequired,
                        'notes': w.Notes
                    } for w in warnings]
                }
            else:
                # Get all active warnings
                warnings = self.warning_service.get_all_active_warnings()
                
                return {
                    'warnings': [{
                        'id': w.Id,
                        'student_id': w.StudentId,
                        'student_name': w.student.Name if w.student else 'غير معروف',
                        'type': w.WarningType,
                        'type_ar': self.warning_service.WARNING_TYPES.get(w.WarningType, w.WarningType),
                        'level': w.WarningLevel,
                        'level_ar': self.warning_service.WARNING_LEVELS.get(w.WarningLevel, str(w.WarningLevel)),
                        'description': w.Description,
                        'semester': w.Semester,
                        'issue_date': w.IssueDate.isoformat() if w.IssueDate else None,
                        'status': w.Status,
                        'action_required': w.ActionRequired
                    } for w in warnings]
                }
                
        except Exception as e:
            logger.error(f"خطأ في جلب الإنذارات: {str(e)}")
            return {'error': 'حدث خطأ في جلب الإنذارات'}, 500
    
    def post(self):
        """تشغيل فحص الإنذارات يدوياً"""
        try:
            data = request.get_json() or {}
            semester = data.get('semester', self.warning_service.get_current_semester())
            
            result = self.warning_service.check_all_students_warnings(semester)
            
            # التعامل مع الاستجابة الجديدة
            if isinstance(result, dict):
                if 'error' in result:
                    return {'error': f'حدث خطأ في فحص الإنذارات: {result["error"]}'}, 500
                
                return {
                    'message': f'تم فحص الطلاب - إصدار {result["warnings_issued"]} إنذار وحل {result["warnings_resolved"]} إنذار',
                    'warnings_issued': result['warnings_issued'],
                    'warnings_resolved': result['warnings_resolved'],
                    'total_processed': result['total_processed'],
                    'semester': semester
                }
            else:
                # للتوافق مع النسخة القديمة
                return {
                    'message': f'تم فحص الطلاب وإصدار {result} إنذار',
                    'warnings_issued': result,
                    'warnings_resolved': 0,
                    'total_processed': result,
                    'semester': semester
                }
            
        except Exception as e:
            logger.error(f"خطأ في تشغيل فحص الإنذارات: {str(e)}")
            return {'error': 'حدث خطأ في تشغيل فحص الإنذارات'}, 500


class ResolveWarningResource(Resource):
    
    def __init__(self):
        self.warning_service = AcademicWarningService()
    
    def put(self, warning_id):
        """حل إنذار أكاديمي"""
        try:
            data = request.get_json() or {}
            notes = data.get('notes', '')
            
            success = self.warning_service.resolve_warning(warning_id, notes)
            
            if success:
                return {'message': 'تم حل الإنذار بنجاح'}
            else:
                return {'error': 'فشل في حل الإنذار'}, 400
                
        except Exception as e:
            logger.error(f"خطأ في حل الإنذار: {str(e)}")
            return {'error': 'حدث خطأ في حل الإنذار'}, 500


class WarningStatsResource(Resource):
    
    def __init__(self):
        self.warning_service = AcademicWarningService()
    
    def get(self):
        """إحصائيات الإنذارات الأكاديمية"""
        try:
            # إحصائيات عامة
            total_active = AcademicWarnings.query.filter_by(Status='نشط').count()
            total_resolved = AcademicWarnings.query.filter_by(Status='محلول').count()
            
            # إحصائيات حسب النوع
            warning_types_stats = db.session.query(
                AcademicWarnings.WarningType,
                func.count(AcademicWarnings.Id).label('count')
            ).filter_by(Status='نشط').group_by(AcademicWarnings.WarningType).all()
            
            # إحصائيات حسب المستوى
            warning_levels_stats = db.session.query(
                AcademicWarnings.WarningLevel,
                func.count(AcademicWarnings.Id).label('count')
            ).filter_by(Status='نشط').group_by(AcademicWarnings.WarningLevel).all()
            
            return {
                'summary': {
                    'total_active': total_active,
                    'total_resolved': total_resolved,
                    'total_all': total_active + total_resolved
                },
                'by_type': [{
                    'type': wt[0],
                    'type_ar': self.warning_service.WARNING_TYPES.get(wt[0], wt[0]),
                    'count': wt[1]
                } for wt in warning_types_stats],
                'by_level': [{
                    'level': wl[0],
                    'level_ar': self.warning_service.WARNING_LEVELS.get(wl[0], str(wl[0])),
                    'count': wl[1]
                } for wl in warning_levels_stats]
            }
            
        except Exception as e:
            logger.error(f"خطأ في جلب إحصائيات الإنذارات: {str(e)}")
            return {'error': 'حدث خطأ في جلب الإحصائيات'}, 500


class StudentWarningCheckResource(Resource):
    
    def __init__(self):
        self.warning_service = AcademicWarningService()
    
    def post(self, student_id):
        """فحص إنذارات طالب معين"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {'error': 'الطالب غير موجود'}, 404
            
            data = request.get_json() or {}
            semester = data.get('semester', self.warning_service.get_current_semester())
            
            # فحص وحل الإنذارات المحسنة أولاً
            resolved_count = self.warning_service.check_and_resolve_warnings(student_id)
            
            # تقييم الطالب للإنذارات الجديدة
            warnings = self.warning_service._evaluate_student_warnings(student, semester)
            warnings_issued = 0
            
            # إصدار الإنذارات الجديدة
            for warning in warnings:
                if self.warning_service._should_issue_warning(student, warning):
                    self.warning_service._create_warning(student, warning, semester)
                    warnings_issued += 1
            
            return {
                'message': f'تم فحص الطالب {student.Name} - إصدار {warnings_issued} إنذار وحل {resolved_count} إنذار',
                'student_name': student.Name,
                'warnings_issued': warnings_issued,
                'warnings_resolved': resolved_count,
                'potential_warnings': len(warnings),
                'semester': semester
            }
            
        except Exception as e:
            logger.error(f"خطأ في فحص إنذارات الطالب: {str(e)}")
            return {'error': 'حدث خطأ في فحص إنذارات الطالب'}, 500


class StudentWarningResolveResource(Resource):
    
    def __init__(self):
        self.warning_service = AcademicWarningService()
    
    def post(self, student_id):
        """فحص وحل إنذارات طالب معين تلقائياً"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {'error': 'الطالب غير موجود'}, 404
            
            resolved_count = self.warning_service.check_and_resolve_warnings(student_id)
            
            return {
                'message': f'تم فحص وحل {resolved_count} إنذار للطالب {student.Name}',
                'student_name': student.Name,
                'warnings_resolved': resolved_count
            }
            
        except Exception as e:
            logger.error(f"خطأ في حل إنذارات الطالب: {str(e)}")
            return {'error': 'حدث خطأ في حل إنذارات الطالب'}, 500

class AcademicStatusAnalysisResource(Resource):
    """
    API Resource for comprehensive academic status analysis
    """
    
    def get(self, student_id):
        """
        Get comprehensive academic status analysis for a student
        """
        try:
            analysis = AcademicStatusAnalysisService.get_comprehensive_analysis(student_id)
            
            if "error" in analysis:
                return {
                    "success": False,
                    "message": analysis["error"],
                    "data": None
                }, 404
            
            return {
                "success": True,
                "message": "تم تحليل الوضع الأكاديمي بنجاح",
                "data": analysis,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تحليل الوضع الأكاديمي: {str(e)}",
                "data": None
            }, 500

class StudentBasicInfoResource(Resource):
    """API Resource for student basic information"""
    
    def get(self, student_id):
        try:
            from models import Students
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود",
                    "data": None
                }, 404
            
            basic_info = AcademicStatusAnalysisService._get_student_basic_info(student)
            
            return {
                "success": True,
                "message": "تم جلب المعلومات الأساسية بنجاح",
                "data": basic_info,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في جلب المعلومات الأساسية: {str(e)}",
                "data": None
            }, 500

class GPAAnalysisResource(Resource):
    """API Resource for GPA trend analysis"""
    
    def get(self, student_id):
        try:
            gpa_analysis = AcademicStatusAnalysisService._analyze_gpa_trends(student_id)
            
            return {
                "success": True,
                "message": "تم تحليل اتجاهات المعدل بنجاح",
                "data": gpa_analysis,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تحليل المعدل: {str(e)}",
                "data": None
            }, 500

class PerformancePatternsResource(Resource):
    """API Resource for performance patterns analysis"""
    
    def get(self, student_id):
        try:
            performance_patterns = AcademicStatusAnalysisService._analyze_performance_patterns(student_id)
            
            return {
                "success": True,
                "message": "تم تحليل أنماط الأداء بنجاح",
                "data": performance_patterns,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تحليل أنماط الأداء: {str(e)}",
                "data": None
            }, 500

class RiskAssessmentResource(Resource):
    """API Resource for academic risk assessment"""
    
    def get(self, student_id):
        try:
            risk_assessment = AcademicStatusAnalysisService._calculate_risk_assessment(student_id)
            
            return {
                "success": True,
                "message": "تم تقييم المخاطر الأكاديمية بنجاح",
                "data": risk_assessment,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تقييم المخاطر: {str(e)}",
                "data": None
            }, 500

class CourseAnalysisResource(Resource):
    """API Resource for course performance analysis"""
    
    def get(self, student_id):
        try:
            course_analysis = AcademicStatusAnalysisService._analyze_course_performance(student_id)
            
            return {
                "success": True,
                "message": "تم تحليل أداء المواد بنجاح",
                "data": course_analysis,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تحليل أداء المواد: {str(e)}",
                "data": None
            }, 500

class AttendanceAnalysisResource(Resource):
    """API Resource for attendance analysis"""
    
    def get(self, student_id):
        try:
            attendance_insights = AcademicStatusAnalysisService._analyze_attendance_patterns(student_id)
            
            return {
                "success": True,
                "message": "تم تحليل الحضور بنجاح",
                "data": attendance_insights,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تحليل الحضور: {str(e)}",
                "data": None
            }, 500

class AcademicWarningsSummaryResource(Resource):
    """API Resource for academic warnings summary"""
    
    def get(self, student_id):
        try:
            warnings_summary = AcademicStatusAnalysisService._get_warnings_summary(student_id)
            
            return {
                "success": True,
                "message": "تم جلب ملخص الإنذارات بنجاح",
                "data": warnings_summary,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في جلب ملخص الإنذارات: {str(e)}",
                "data": None
            }, 500

class PeerComparisonResource(Resource):
    """API Resource for peer comparison analysis"""
    
    def get(self, student_id):
        try:
            peer_comparison = AcademicStatusAnalysisService._compare_with_peers(student_id)
            
            return {
                "success": True,
                "message": "تم تحليل المقارنة مع الزملاء بنجاح",
                "data": peer_comparison,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في تحليل المقارنة مع الزملاء: {str(e)}",
                "data": None
            }, 500

class PredictionsResource(Resource):
    """API Resource for academic predictions"""
    
    def get(self, student_id):
        try:
            predictions = AcademicStatusAnalysisService._get_merged_predictions(student_id)
            
            return {
                "success": True,
                "message": "تم توليد التوقعات الأكاديمية بنجاح",
                "data": predictions,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في توليد التوقعات: {str(e)}",
                "data": None
            }, 500

class InterventionsResource(Resource):
    """API Resource for predictive interventions"""
    
    def get(self, student_id):
        try:
            interventions = AcademicStatusAnalysisService._predictive_intervention_system(student_id)
            
            return {
                "success": True,
                "message": "تم توليد التدخلات الوقائية بنجاح",
                "data": interventions,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في توليد التدخلات الوقائية: {str(e)}",
                "data": None
            }, 500

class AIInsightsResource(Resource):
    """API Resource for AI-generated insights"""
    
    def get(self, student_id):
        try:
            ai_insights = AcademicStatusAnalysisService._generate_ai_insights(student_id)
            
            return {
                "success": True,
                "message": "تم توليد الرؤى الذكية بنجاح",
                "data": ai_insights,
                "timestamp": datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {
                "success": False,
                "message": f"خطأ في توليد الرؤى الذكية: {str(e)}",
                "data": None
            }, 500

class AcademicPathPlanningResource(Resource):
    """مورد التخطيط الأكاديمي للمسارات"""
    
    def __init__(self):
        self.path_service = AcademicPathService()
    
    def get(self, student_id):
        """الحصول على الخطة الأكاديمية الكاملة للطالب"""
        try:
            result = self.path_service.get_student_academic_path(student_id)
            
            if not result:
                return {'message': 'الطالب غير موجود'}, 404
            
            return result, 200
            
        except Exception as e:
            return {'message': f'خطأ في استرجاع الخطة الأكاديمية: {str(e)}'}, 500


class PathRecommendationResource(Resource):
    """مورد توصيات التشعيبات"""
    
    def __init__(self):
        self.recommendation_service = DivisionRecommendationService()
    
    def get(self, student_id):
        """الحصول على توصيات التشعيب المفصلة للطالب"""
        try:
            result = self.recommendation_service.get_division_recommendations(student_id)
            
            if not result:
                return {'message': 'الطالب غير موجود'}, 404
            
            return result, 200
            
        except Exception as e:
            return {'message': f'خطأ في توليد التوصيات: {str(e)}'}, 500


class StudentPathProgressResource(Resource):
    """مورد متابعة تقدم الطالب في المسار"""
    
    def __init__(self):
        self.path_service = AcademicPathService()
    
    def get(self, student_id):
        """الحصول على تقدم الطالب في المسار الأكاديمي"""
        try:
            result = self.path_service.get_student_academic_path(student_id)
            
            if not result:
                return {'message': 'الطالب غير موجود'}, 404
            
            # إرجاع معلومات التقدم فقط
            return {
                'student_info': result['student_info'],
                'progress': result['progress'],
                'current_path': result['current_path']
            }, 200
            
        except Exception as e:
            return {'message': f'خطأ في استرجاع تقدم الطالب: {str(e)}'}, 500


class PathValidationResource(Resource):
    """مورد التحقق من صحة المسار الأكاديمي"""
    
    def __init__(self):
        self.path_service = AcademicPathService()
    
    def get(self, student_id):
        """التحقق من صحة المسار الأكاديمي للطالب"""
        try:
            result = self.path_service.get_student_academic_path(student_id)
            
            if not result:
                return {'message': 'الطالب غير موجود'}, 404
            
            # التحقق من صحة المسار
            validation_result = {
                'student_id': student_id,
                'is_valid_path': True,
                'validation_issues': [],
                'recommendations': [],
                'eligibility': result['progress']['transition_eligibility']
            }
            
            # فحص المشاكل المحتملة
            progress = result['progress']
            
            # فحص المعدل التراكمي
            if progress['cumulative_gpa']['current_cumulative'] < 2.0:
                validation_result['is_valid_path'] = False
                validation_result['validation_issues'].append('المعدل التراكمي أقل من الحد الأدنى المطلوب')
                validation_result['recommendations'].append('ضرورة تحسين المعدل التراكمي قبل المتابعة')
            
            # فحص الساعات المكتملة
            expected_credits = progress['current_year'] * 30
            if progress['credits_completed'] < expected_credits * 0.8:  # 80% من الساعات المتوقعة
                validation_result['validation_issues'].append('نقص في الساعات المكتملة مقارنة بالمتوقع')
                validation_result['recommendations'].append('زيادة عدد الساعات المسجلة في الفصول القادمة')
            
            # فحص التقدم في المسار
            if not progress['next_available_divisions']:
                current_year = progress['current_year']
                if current_year >= 2:  # يجب أن تكون هناك خيارات متاحة
                    validation_result['validation_issues'].append('لا توجد تشعيبات متاحة للانتقال')
                    validation_result['recommendations'].append('مراجعة المرشد الأكاديمي لتحديد الخيارات المتاحة')
            
            return validation_result, 200
            
        except Exception as e:
            return {'message': f'خطأ في التحقق من صحة المسار: {str(e)}'}, 500


class DivisionTransitionResource(Resource):
    """مورد طلبات الانتقال بين التشعيبات"""
    
    def __init__(self):
        self.path_service = AcademicPathService()
        self.recommendation_service = DivisionRecommendationService()
    
    def get(self, student_id):
        """الحصول على معلومات الانتقال المتاحة للطالب"""
        try:
            # الحصول على التشعيبات المتاحة
            path_result = self.path_service.get_student_academic_path(student_id)
            
            if not path_result:
                return {'message': 'الطالب غير موجود'}, 404
            
            # الحصول على توصيات التشعيب
            recommendations = self.recommendation_service.get_division_recommendations(student_id)
            
            transition_info = {
                'student_id': student_id,
                'current_division': path_result['student_info']['division_name'],
                'available_transitions': path_result['progress']['next_available_divisions'],
                'eligibility': path_result['progress']['transition_eligibility'],
                'recommendations': recommendations['recommendations'] if recommendations else [],
                'transition_requirements': self._get_transition_requirements(),
                'deadlines': self._get_transition_deadlines()
            }
            
            return transition_info, 200
            
        except Exception as e:
            return {'message': f'خطأ في استرجاع معلومات الانتقال: {str(e)}'}, 500
    
    def post(self, student_id):
        """تقديم طلب انتقال لتشعيب جديد"""
        try:
            data = request.get_json()
            
            if not data or 'target_division_id' not in data:
                return {'message': 'معرف التشعيب المطلوب مطلوب'}, 400
            
            target_division_id = data['target_division_id']
            reason = data.get('reason', '')
            
            # التحقق من صحة الطلب
            validation_result = self._validate_transition_request(student_id, target_division_id)
            
            if not validation_result['is_valid']:
                return {
                    'message': 'طلب الانتقال غير صالح',
                    'errors': validation_result['errors']
                }, 400
            
            # في التطبيق الحقيقي، هنا سيتم حفظ الطلب في قاعدة البيانات
            # لكن حالياً سنرجع رسالة نجاح فقط
            
            return {
                'message': 'تم تقديم طلب الانتقال بنجاح',
                'request_id': f'TR_{student_id}_{target_division_id}_{int(datetime.now().timestamp())}',
                'status': 'pending_review',
                'submitted_at': datetime.now().isoformat(),
                'target_division_id': target_division_id,
                'reason': reason
            }, 201
            
        except Exception as e:
            return {'message': f'خطأ في تقديم طلب الانتقال: {str(e)}'}, 500
    
    def _validate_transition_request(self, student_id, target_division_id):
        """التحقق من صحة طلب الانتقال"""
        validation_result = {
            'is_valid': True,
            'errors': []
        }
        
        try:
            # الحصول على معلومات الطالب
            path_result = self.path_service.get_student_academic_path(student_id)
            
            if not path_result:
                validation_result['is_valid'] = False
                validation_result['errors'].append('الطالب غير موجود')
                return validation_result
            
            # التحقق من أهلية الانتقال
            eligibility = path_result['progress']['transition_eligibility']
            if not eligibility['is_eligible']:
                validation_result['is_valid'] = False
                validation_result['errors'].extend(eligibility['requirements_missing'])
            
            # التحقق من أن التشعيب المطلوب متاح
            available_divisions = path_result['progress']['next_available_divisions']
            available_division_ids = [div['id'] for div in available_divisions]
            
            if target_division_id not in available_division_ids:
                validation_result['is_valid'] = False
                validation_result['errors'].append('التشعيب المطلوب غير متاح للانتقال')
            
            return validation_result
            
        except Exception as e:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f'خطأ في التحقق من الطلب: {str(e)}')
            return validation_result
    
    def _get_transition_requirements(self):
        """متطلبات الانتقال العامة"""
        return {
            'minimum_gpa': 2.0,
            'minimum_credits': 'حسب السنة الأكاديمية',
            'application_deadline': 'نهاية الأسبوع الثاني من الفصل الدراسي',
            'required_documents': [
                'استمارة طلب الانتقال',
                'كشف الدرجات',
                'موافقة المرشد الأكاديمي'
            ]
        }
    
    def _get_transition_deadlines(self):
        """مواعيد تقديم طلبات الانتقال"""
        return {
            'fall_semester': 'نهاية سبتمبر',
            'spring_semester': 'نهاية فبراير',
            'summer_semester': 'نهاية يونيو',
            'note': 'يجب تقديم الطلب قبل بداية الفصل الدراسي بأسبوعين على الأقل'
        }


class VerySmartAcademicPathPlanningResource(Resource):
    """مورد التخطيط الأكاديمي الذكي المتقدم"""
    
    def __init__(self):
        self.smart_service = VerySmartAcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على الخطة الأكاديمية الذكية المتقدمة للطالب"""
        try:
            result = self.smart_service.get_very_smart_academic_plan(student_id)
            
            if 'error' in result:
                return {'message': result['error']}, 404 if 'غير موجود' in result['error'] else 500
            
            return result, 200
            
        except Exception as e:
            return {'message': f'خطأ في استرجاع الخطة الذكية: {str(e)}'}, 500


class SmartPathAnalysisResource(Resource):
    """مورد التحليل الذكي للمسار الأكاديمي"""
    
    def __init__(self):
        self.smart_service = VerySmartAcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على التحليل الذكي فقط بدون الخطة الكاملة"""
        try:
            # الحصول على البيانات الشاملة
            comprehensive_data = self.smart_service._gather_comprehensive_data(student_id)
            
            if 'error' in comprehensive_data:
                return {'message': comprehensive_data['error']}, 404 if 'غير موجود' in comprehensive_data['error'] else 500
            
            # تطبيق التحليل الذكي فقط
            ai_analysis = self.smart_service._apply_ai_analysis(comprehensive_data)
            
            return {
                'student_id': student_id,
                'data_quality': comprehensive_data.get('data_quality', {}),
                'ai_analysis': ai_analysis,
                'generated_at': datetime.now().isoformat()
            }, 200
            
        except Exception as e:
            return {'message': f'خطأ في التحليل الذكي: {str(e)}'}, 500


class AcademicSmartRecommendationsResource(Resource):
    """مورد التوصيات الذكية الأكاديمية"""
    
    def __init__(self):
        self.smart_service = VerySmartAcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على التوصيات الذكية المخصصة للطالب"""
        try:
            # الحصول على الخطة الأكاديمية الكاملة
            full_plan = self.smart_service.get_very_smart_academic_plan(student_id)
            
            if 'error' in full_plan:
                return full_plan, 404
            
            # استخراج التوصيات المهمة
            recommendations = {
                'student_id': student_id,
                'smart_plan_summary': full_plan.get('smart_academic_plan', {}).get('plan_summary', {}),
                'optimization_recommendations': full_plan.get('optimization_recommendations', {}),
                'ai_insights': {
                    'learning_patterns': full_plan.get('ai_insights', {}).get('learning_patterns', {}),
                    'risk_analysis': full_plan.get('ai_insights', {}).get('risk_analysis', {}),
                    'career_alignment': full_plan.get('ai_insights', {}).get('career_alignment', {})
                },
                'future_predictions': full_plan.get('future_predictions', {}),
                'priority_actions': self._extract_priority_actions(full_plan),
                'generated_at': datetime.now().isoformat()
            }
            
            return recommendations, 200
            
        except Exception as e:
            return {'message': f'خطأ في الحصول على التوصيات الذكية: {str(e)}'}, 500
    
    def _extract_priority_actions(self, full_plan):
        """استخراج الإجراءات ذات الأولوية"""
        priority_actions = []
        
        # من الخطة قصيرة المدى
        short_term = full_plan.get('smart_academic_plan', {}).get('short_term', {})
        priority_actions.extend(short_term.get('priorities', [])[:3])
        
        # من تحليل المخاطر
        risk_analysis = full_plan.get('ai_insights', {}).get('risk_analysis', {})
        if risk_analysis.get('level') in ['عالي', 'عالي جداً']:
            priority_actions.extend(risk_analysis.get('mitigation_strategies', [])[:2])
        
        return priority_actions[:5]  # أول 5 إجراءات


class StudentPerformancePredictionResource(Resource):
    """مورد التنبؤ بأداء الطالب"""
    
    def __init__(self):
        self.smart_service = VerySmartAcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على تنبؤات الأداء للطالب"""
        try:
            # الحصول على البيانات والتحليل
            comprehensive_data = self.smart_service._gather_comprehensive_data(student_id)
            
            if 'error' in comprehensive_data:
                return {'message': comprehensive_data['error']}, 404 if 'غير موجود' in comprehensive_data['error'] else 500
            
            ai_analysis = self.smart_service._apply_ai_analysis(comprehensive_data)
            future_predictions = self.smart_service._predict_future_paths(comprehensive_data, ai_analysis)
            
            predictions = {
                'student_id': student_id,
                'performance_prediction': ai_analysis.get('performance_prediction', {}),
                'future_paths': future_predictions,
                'risk_analysis': ai_analysis.get('risk_analysis', {}),
                'opportunities_threats': ai_analysis.get('opportunities_threats', {}),
                'confidence_metrics': {
                    'data_quality_score': comprehensive_data.get('data_quality', {}).get('score', 0),
                    'prediction_confidence': ai_analysis.get('performance_prediction', {}).get('confidence_level', 0),
                    'overall_ai_score': ai_analysis.get('overall_ai_score', {}).get('score', 0)
                },
                'generated_at': datetime.now().isoformat()
            }
            
            return predictions, 200
            
        except Exception as e:
            return {'message': f'خطأ في التنبؤ بالأداء: {str(e)}'}, 500 