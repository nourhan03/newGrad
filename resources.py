from flask import request
from datetime import datetime
from flask import request, jsonify
from models import AcademicWarnings, Students
from extensions import db
from flask_restful import Resource
from services import(
    AcademicPathPlanningService,
    AcademicStatusAnalysisService,
    AcademicStatusAnalysisService,
    AcademicWarningService,
    CourseEnrollmentService,
    SmartCourseRecommendationService,
    EnrollmentPeriodService,
    GraduationEligibilityService
    
) 

import logging

logger = logging.getLogger(__name__)




class GraduationEligibilityResource(Resource):
    
    def get(self, student_id):
        try:
            if not student_id or student_id <= 0:
                return {
                    "success": False,
                    "message": "معرف الطالب غير صحيح",
                    "error": "INVALID_STUDENT_ID"
                }, 400
            
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
    
    def get(self, student_id):        
        try:
            if not student_id or student_id <= 0:
                return {
                    "success": False,
                    "message": "معرف الطالب غير صحيح",
                    "error": "INVALID_STUDENT_ID"
                }, 400
            
            full_result = GraduationEligibilityService.get_graduation_eligibility(student_id)
            
            if not full_result["success"]:
                return full_result, 404 if "STUDENT_NOT_FOUND" in full_result.get("error", "") else 500
            
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
                    "active_warnings": full_result["academic_warnings"].get("count", 0)
                },
                "top_recommendations": full_result["recommendations"][:3],  
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
            
            # فحص إذا كانت فترة التسجيل مقفولة
            if recommendations.get('enrollment_closed'):
                return {
                    'enrollment_closed': True,
                    'message': recommendations.get('message'),
                    'period_info': recommendations.get('period_info'),
                    'data': None
                }, 200
            
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
            
            # فحص فترة التسجيل أولاً
            enrollment_status = self.service._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'data': None
                }, 200
            
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
                    'available_seats': original_course.get('available_seats', 
                                      original_course.get('max_seats', 100) - original_course.get('current_enrolled', 0)),
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
            
            # فحص فترة التسجيل أولاً
            enrollment_status = self.service._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'data': None
                }, 200
            
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
                    'available_seats': original_course.get('available_seats', 
                                      original_course.get('max_seats', 100) - original_course.get('current_enrolled', 0)),
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
            
            # فحص فترة التسجيل أولاً
            enrollment_status = self.service._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'data': None
                }, 200
            
            recommendations = self.service.get_smart_recommendations(student_id)
            
            if isinstance(recommendations, tuple):
                error_data, status_code = recommendations
                return {
                    
                    'data': None
                }, status_code
            
            failed_courses_data = recommendations.get('failed_courses_retry', {})
            
            if isinstance(failed_courses_data, dict):
                courses = failed_courses_data.get('courses', [])
                clean_courses = []
                
                for course_rec in courses:
                    original_course = course_rec.get('course', {})
                    
                    clean_course = {
                        'id': original_course.get('id'),
                        'name': original_course.get('name'),
                        'code': original_course.get('code'),
                        'description': original_course.get('description'),
                        'credits': original_course.get('credits'),
                        'available_seats': original_course.get('available_seats', 
                                          original_course.get('max_seats', 100) - original_course.get('current_enrolled', 0)),
                        'professor_name': original_course.get('professor_name'),
                        'day_name': original_course.get('day_name'),
                        'start_time': original_course.get('start_time'),
                        'end_time': original_course.get('end_time'),
                        'location': original_course.get('location')
                    }
                    
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
            
            # فحص فترة التسجيل أولاً
            enrollment_status = self.service._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'data': None
                }, 200
            
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
            
            # فحص فترة التسجيل أولاً
            enrollment_status = service._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'data': None
                }, 200
            
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
                    
                    clean_course = {
                        'id': course.get('id'),
                        'name': course.get('name'),
                        'code': course.get('code'),
                        'description': course.get('description'),
                        'credits': course.get('credits'),
                        'available_seats': course.get('available_seats', 
                                          course.get('max_seats', 100) - course.get('current_enrolled', 0)),
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
            
            # فحص فترة التسجيل أولاً
            enrollment_status = service._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'data': None
                }, 200
            
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
                    
                    clean_course = {
                        'id': course.get('id'),
                        'name': course.get('name'),
                        'code': course.get('code'),
                        'description': course.get('description'),
                        'credits': course.get('credits'),
                        'available_seats': course.get('available_seats', 
                                          course.get('max_seats', 100) - course.get('current_enrolled', 0)),
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
    
    def post(self, student_id):
        try:
            data = request.get_json()
            
            if not data or 'course_id' not in data:
                return {
                    "success": False,
                    "message": "يجب تحديد معرف المادة (course_id)"
                }, 400
            
            course_id = data['course_id']
            
            if not isinstance(course_id, int) or course_id <= 0:
                return {
                    "success": False,
                    "message": "معرف المادة غير صحيح"
                }, 400
            
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
    
    def put(self, student_id):
        try:
            data = request.get_json()
            
            if not data or 'enrollment_id' not in data:
                return {
                    "success": False,
                    "message": "يجب تحديد معرف التسجيل (enrollment_id)"
                }, 400
            
            enrollment_id = data['enrollment_id']
            
            if not isinstance(enrollment_id, int) or enrollment_id <= 0:
                return {
                    "success": False,
                    "message": "معرف التسجيل غير صحيح"
                }, 400
            
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
    
    def delete(self, enrollment_id):
        try:
            if not isinstance(enrollment_id, int) or enrollment_id <= 0:
                return {
                    "success": False,
                    "message": "معرف التسجيل غير صحيح"
                }, 400
            
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
    
    def get(self, student_id):
        try:
            result = CourseEnrollmentService.get_student_enrollments(student_id)
            
            if result["success"]:
                data = result["data"]
                
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
        try:
            if student_id:
                status = request.args.get('status')
                warnings = self.warning_service.get_student_warnings(student_id, status)
                
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
            from sqlalchemy import func
            from models import AcademicWarnings
            
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
    def get(self, student_id):
  
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
    """موقع API للحصول على الخطة الأكاديمية الشاملة للطالب"""
    
    def __init__(self):
        self.service = AcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على الخطة الأكاديمية الشاملة للطالب"""
        try:
            result = self.service.get_academic_plan(student_id)
            
            if 'error' in result:
                return {'message': result['error'], 'status': 'error'}, 404
            
            return {
                'message': 'تم الحصول على الخطة الأكاديمية بنجاح',
                'status': 'success',
                'data': result
            }, 200
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على الخطة الأكاديمية: {str(e)}")
            return {
                'message': f'حدث خطأ أثناء الحصول على الخطة الأكاديمية: {str(e)}',
                'status': 'error'
            }, 500


class DivisionRecommendationResource(Resource):
    """موقع API لاقتراح الشعبة/التخصص للطالب"""
    
    def __init__(self):
        self.service = AcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على توصية الشعبة/التخصص للطالب"""
        try:
            result = self.service.get_division_recommendations(student_id)
            
            if 'error' in result:
                return {'message': result['error'], 'status': 'error'}, 404
            
            return {
                'message': 'تم الحصول على توصيات التخصص بنجاح',
                'status': 'success',
                'data': result
            }, 200
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على توصيات التخصص: {str(e)}")
            return {
                'message': f'حدث خطأ أثناء الحصول على توصيات التخصص: {str(e)}',
                'status': 'error'
            }, 500


class CourseScheduleResource(Resource):
    """موقع API للحصول على جدولة المقررات للفصول القادمة"""
    
    def __init__(self):
        self.service = AcademicPathPlanningService()
    
    def get(self, student_id):
        """الحصول على جدولة المقررات للفصول القادمة"""
        try:
            semester_count = request.args.get('semester_count', 2, type=int)
            result = self.service.get_course_schedule(student_id, semester_count)
            
            if 'error' in result:
                return {'message': result['error'], 'status': 'error'}, 404
            
            return {
                'message': f'تم الحصول على جدولة المقررات بنجاح',
                'status': 'success',
                'data': result
            }, 200
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على جدولة المقررات: {str(e)}")
            return {
                'message': f'حدث خطأ أثناء الحصول على جدولة المقررات: {str(e)}',
                'status': 'error'
            }, 500


class StudentPerformanceAnalysisResource(Resource):
    """موقع API لتحليل أداء الطالب الأكاديمي"""
    
    def __init__(self):
        self.service = AcademicPathPlanningService()
    
    def get(self, student_id):
        """تحليل أداء الطالب الأكاديمي"""
        try:
            result = self.service.analyze_student_performance(student_id)
            
            if 'error' in result:
                return {'message': result['error'], 'status': 'error'}, 404
            
            return {
                'message': 'تم تحليل أداء الطالب بنجاح',
                'status': 'success',
                'data': result
            }, 200
            
        except Exception as e:
            logger.error(f"خطأ في تحليل أداء الطالب: {str(e)}")
            return {
                'message': f'حدث خطأ أثناء تحليل أداء الطالب: {str(e)}',
                'status': 'error'
            }, 500 
