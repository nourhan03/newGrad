from datetime import datetime
from sqlalchemy import func, and_
from extensions import db
from models import Students, Divisions, Enrollments, Courses, CourseDivisions, Departments,Professors
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import statistics
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pandas as pd

from models import (
    Students, Enrollments, Courses, AcademicWarnings, 
    Attendances, Divisions, db
)

from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
from extensions import db
from models import Students, Enrollments, Courses, AcademicWarnings
import logging
from models import Students, Courses, Enrollments, EnrollmentPeriods, CourseDivisions, CoursePrerequisites
import logging

logger = logging.getLogger(__name__)

from models import EnrollmentPeriods



class GraduationEligibilityService:
    
    # ثوابت النظام الأكاديمي
    TOTAL_REQUIRED_CREDITS = 136
    MANDATORY_CREDITS = 96
    ELECTIVE_CREDITS = 40
    MINIMUM_GPA = 2.0
    
    # تصنيف السنوات الدراسية
    YEAR_CLASSIFICATIONS = {
        1: (0, 33),    
        2: (34, 67),    
        3: (68, 101),  # السنة الثالثة
        4: (102, 136)  # السنة الرابعة
    }
    
    # المسارات الأكاديمية
    ACADEMIC_TRACKS = {
        "العلوم الطبيعية": {
            "year_1": [1030],  # مجموعة العلوم الطبيعية
            "year_2": [1035, 1095],  # الرياضيات والفيزياء، الكيمياء والفيزياء
            "year_3_4_math_physics": [1040, 1045, 1035, 1050],
            "year_3_4_chem_physics": [1055, 1095]
        },
        "العلوم البيولوجية": {
            "year_1_2": [1085],  # مجموعة العلوم البيولوجية والكيميائية
            "year_3_4": [1060, 1065, 1070, 1075]
        },
        "العلوم الجيولوجية": {
            "year_1_2": [1090],  # مجموعة العلوم الجيولوجية والكيميائية
            "year_3_4": [1080]
        }
    }

    @classmethod
    def get_graduation_eligibility(cls, student_id):
        """الحصول على تقرير أهلية التخرج الشامل"""
        try:
            # الحصول على بيانات الطالب
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود"
                    
                }
            
            # معلومات الطالب
            student_info = cls._get_student_info(student)
            
            # حساب المعدل التراكمي
            cumulative_gpa = cls._calculate_gpa(student_id)
            
            # الحصول على المواد والساعات
            completed_courses = cls._get_completed_courses(student_id)
            failed_courses = cls._get_failed_courses(student_id)
            remaining_courses = cls._get_remaining_courses(student_id, student.DivisionId)
            
            # تحليل الساعات مع تمرير الساعات الفعلية للطالب
            credits_analysis = cls._analyze_credits(
                completed_courses, 
                remaining_courses, 
                student.DivisionId,
                student.CreditsCompleted
            )
            
            # تحليل المعدل
            gpa_analysis = cls._analyze_gpa(cumulative_gpa)
            
            # الإنذارات الأكاديمية
            warnings = cls._get_academic_warnings(student_id)
            
            # تحديد حالة التخرج
            graduation_status = cls._determine_graduation_status(
                credits_analysis, cumulative_gpa, warnings
            )
            
            # التخطيط للتخرج
            graduation_planning = cls._calculate_graduation_planning(
                credits_analysis, student_info["current_semester"]
            )
            
            # التوصيات
            recommendations = cls._generate_recommendations(
                graduation_status, credits_analysis, gpa_analysis, remaining_courses
            )
            
            return {
                "success": True,
                "message": "تم الحصول على تقرير أهلية التخرج بنجاح",
                "student_info": student_info,
                "graduation_status": graduation_status,
                "credits_analysis": credits_analysis,
                "gpa_analysis": gpa_analysis,
                "completed_courses": completed_courses,
                "failed_courses": failed_courses,
                "remaining_courses": remaining_courses,
                "academic_warnings": warnings,
                "graduation_planning": graduation_planning,
                "recommendations": recommendations,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in get_graduation_eligibility: {str(e)}")
            return {
                "success": False,
                "message": "حدث خطأ أثناء الحصول على تقرير أهلية التخرج",
                "error": str(e)
            }

    @staticmethod
    def _get_student_info(student):
        """الحصول على معلومات الطالب الأساسية"""
        # استخدام StudentLevel الموجود في الجدول
        academic_year = student.StudentLevel or 1
        
        # الحصول على معلومات الشعبة
        division = Divisions.query.get(student.DivisionId)
        division_name = division.Name if division else "غير محدد"
        
        return {
            "id": student.Id,
            "name": student.Name,
            "division": division_name,
            "current_semester": student.Semester,
            "academic_year": academic_year,
            "status": student.status,
            "credits_completed": student.CreditsCompleted
        }

    @staticmethod
    def _analyze_credits(completed_courses, remaining_courses, division_id, actual_credits=None):
        """تحليل الساعات المكتملة والمتبقية مع مراعاة البيانات الناقصة"""
        
        # حساب الساعات من المواد المسجلة
        calculated_credits = sum(course["credits"] for course in completed_courses)
        
        # استخدام الساعات الفعلية إذا كانت متوفرة وأكبر من المحسوبة
        if actual_credits and actual_credits > calculated_credits:
            completed_credits = actual_credits
            data_source = "ملف الطالب (بيانات مكتملة)"
            # تقدير توزيع الساعات بناءً على النسب المعتادة
            estimated_mandatory = min(GraduationEligibilityService.MANDATORY_CREDITS, int(actual_credits * 0.75))
            estimated_elective = actual_credits - estimated_mandatory
        else:
            completed_credits = calculated_credits
            data_source = "المواد المسجلة"
            # حساب دقيق من المواد المسجلة
            estimated_mandatory = GraduationEligibilityService._calculate_mandatory_credits(completed_courses)
            estimated_elective = completed_credits - estimated_mandatory
        
        # المواد المتبقية
        remaining_credits = sum(course["credits"] for course in remaining_courses)
        
        # حساب الساعات الإجبارية والاختيارية المتبقية
        mandatory_remaining = 0
        elective_remaining = 0
        
        for course in remaining_courses:
            if course["type"] == "إجبارية":
                mandatory_remaining += course["credits"]
            else:
                elective_remaining += course["credits"]
        
        # تعديل الحسابات بناءً على الساعات الفعلية المكتملة
        actual_mandatory_remaining = max(0, GraduationEligibilityService.MANDATORY_CREDITS - estimated_mandatory)
        actual_elective_remaining = max(0, GraduationEligibilityService.ELECTIVE_CREDITS - estimated_elective)
        
        # إجمالي الساعات المتبقية للتخرج
        total_remaining = max(0, GraduationEligibilityService.TOTAL_REQUIRED_CREDITS - completed_credits)
        
        # حساب نسبة الإنجاز
        completion_percentage = (completed_credits / GraduationEligibilityService.TOTAL_REQUIRED_CREDITS) * 100
        
        return {
            "total_required": GraduationEligibilityService.TOTAL_REQUIRED_CREDITS,
            "completed_total": completed_credits,
            "remaining_total": total_remaining,
            "mandatory": {
                "required": GraduationEligibilityService.MANDATORY_CREDITS,
                "completed": estimated_mandatory,
                "remaining": actual_mandatory_remaining
            },
            "elective": {
                "required": GraduationEligibilityService.ELECTIVE_CREDITS,
                "completed": estimated_elective,
                "remaining": actual_elective_remaining
            },
            "completion_percentage": round(completion_percentage, 1),
            "data_source": data_source,
            "note": "الحسابات تعتمد على الساعات المسجلة في ملف الطالب" if actual_credits and actual_credits > calculated_credits else None
        }

    @staticmethod
    def _calculate_mandatory_credits(completed_courses):
        """حساب الساعات الإجبارية المكتملة"""
        try:
            # حساب الساعات الإجبارية من المواد المكتملة
            mandatory_credits = 0
            for course in completed_courses:
                # التحقق من كون المادة إجبارية
                course_division = db.session.query(CourseDivisions).filter(
                    CourseDivisions.CourseId == course["id"],
                    CourseDivisions.IsMandatory == True
                ).first()
                
                if course_division:
                    mandatory_credits += course["credits"]
            
            return mandatory_credits
            
        except Exception as e:
            logger.error(f"Error calculating mandatory credits: {str(e)}")
            return 0

    @staticmethod
    def _analyze_courses(student_id, division_id):
        """تحليل المواد المكتملة والمتبقية"""
        # المواد المكتملة
        completed_courses = GraduationEligibilityService._get_completed_courses(student_id)
        
        # المواد المتبقية
        remaining_courses = GraduationEligibilityService._get_remaining_courses(student_id, division_id)
        
        # المواد الراسبة
        failed_courses = GraduationEligibilityService._get_failed_courses(student_id)
        
        return {
            "completed": completed_courses,
            "remaining": remaining_courses,
            "failed": failed_courses
        }

    @staticmethod
    def _get_completed_courses(student_id):
        """الحصول على المواد المكتملة"""
        try:
            completed = db.session.query(Enrollments, Courses).join(
                Courses, Enrollments.CourseId == Courses.Id
            ).filter(
                Enrollments.StudentId == student_id,
                Enrollments.IsCompleted == "مكتملة"
            ).all()
            
            return [
                {
                    "id": course.Id,
                    "name": course.Name,
                    "code": course.Code,
                    "credits": course.Credits,
                    "grade": (
                        (float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0) +
                        (float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0) +
                        (float(enrollment.Grade) if enrollment.Grade else 0)
                    ),
                    "semester": enrollment.Semester
                }
                for enrollment, course in completed
            ]
        except Exception as e:
            logger.error(f"Error getting completed courses: {str(e)}")
            return []

    @staticmethod
    def _get_remaining_courses(student_id, division_id):
        """الحصول على المواد المتبقية مع تحديد نوعها وحالة توفرها"""
        try:
            # الحصول على المواد المكتملة والمسجل فيها حالياً
            enrolled_course_ids = db.session.query(Enrollments.CourseId).filter(
                Enrollments.StudentId == student_id,
                Enrollments.IsCompleted.in_(["مكتملة", "قيد الدراسة"])
            ).subquery()
            
            # الحصول على جميع مواد الشعبة التي لم يتم التسجيل فيها أو إكمالها
            division_courses = db.session.query(Courses).join(
                CourseDivisions, Courses.Id == CourseDivisions.CourseId
            ).filter(
                CourseDivisions.DivisionId == division_id,
                ~Courses.Id.in_(enrolled_course_ids)
            ).all()
            
            remaining_courses = []
            for course in division_courses:
                # تحديد نوع المادة
                division_course = db.session.query(CourseDivisions).filter(
                    CourseDivisions.DivisionId == division_id,
                    CourseDivisions.CourseId == course.Id
                ).first()
                
                course_type = "إجبارية" if division_course and division_course.IsMandatory else "اختيارية"
                
                # التحقق من حالة توفر المادة من جدول Courses
                is_available = course.Status == "متاح"
                availability_status = "متاحة للتسجيل" if is_available else "غير متاحة حالياً"
                
                # التحقق من المتطلبات السابقة
                prerequisites = GraduationEligibilityService._get_course_prerequisites(course.Id, student_id)
                
                remaining_courses.append({
                    "id": course.Id,
                    "name": course.Name,
                    "code": course.Code,
                    "credits": course.Credits,
                    "type": course_type,
                    "availability_status": availability_status,
                    "prerequisites": prerequisites,
                    "semester": course.Semester,
                })
            
            return remaining_courses
            
        except Exception as e:
            logger.error(f"Error getting remaining courses: {str(e)}")
            return []

    @staticmethod
    def _get_course_prerequisites(course_id, student_id):
        """الحصول على متطلبات المادة والتحقق من إكمالها"""
        try:
            # الحصول على المتطلبات السابقة للمادة
            prerequisites = db.session.query(CoursePrerequisites, Courses).join(
                Courses, CoursePrerequisites.PrerequisiteCourseId == Courses.Id
            ).filter(
                CoursePrerequisites.CourseId == course_id
            ).all()
            
            if not prerequisites:
                return "لا توجد متطلبات سابقة"
            
            # التحقق من إكمال المتطلبات
            completed_course_ids = db.session.query(Enrollments.CourseId).filter(
                Enrollments.StudentId == student_id,
                Enrollments.IsCompleted == "مكتملة"
            ).all()
            
            completed_ids = [c.CourseId for c in completed_course_ids]
            
            prerequisite_info = []
            for prereq, course in prerequisites:
                is_completed = prereq.PrerequisiteCourseId in completed_ids
                prerequisite_info.append({
                    "course_name": course.Name,
                    "course_code": course.Code,
                    "is_completed": is_completed
                })
            
            return prerequisite_info
            
        except Exception as e:
            logger.error(f"Error getting course prerequisites: {str(e)}")
            return "خطأ في تحديد المتطلبات"

    @staticmethod
    def _get_failed_courses(student_id):
        """الحصول على المواد الراسبة"""
        try:
            failed = db.session.query(Enrollments, Courses).join(
                Courses, Enrollments.CourseId == Courses.Id
            ).filter(
                Enrollments.StudentId == student_id,
                Enrollments.IsCompleted == "راسب"
            ).all()
            
            return [
                {
                    "id": course.Id,
                    "name": course.Name,
                    "code": course.Code,
                    "credits": course.Credits,
                    "grade": (
                        (float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0) +
                        (float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0) +
                        (float(enrollment.Grade) if enrollment.Grade else 0)
                    ),
                    "semester": enrollment.Semester,
                    "can_retake": True  # يمكن إعادة المادة الراسبة
                }
                for enrollment, course in failed
            ]
        except Exception as e:
            logger.error(f"Error getting failed courses: {str(e)}")
            return []

    @staticmethod
    def _analyze_gpa(cumulative_gpa):
        """تحليل المعدل التراكمي"""
        # تحديد حالة المعدل
        if cumulative_gpa >= 3.5:
            status = "ممتاز"
            message = "المعدل التراكمي ممتاز. استمر في العمل الجيد!"
        elif cumulative_gpa >= 3.0:
            status = "جيد جداً"
            message = "المعدل التراكمي جيد جداً. حافظ على هذا المستوى!"
        elif cumulative_gpa >= 2.5:
            status = "جيد"
            message = "المعدل التراكمي جيد. يمكنك تحسينه بمزيد من الجهد."
        elif cumulative_gpa >= 2.0:
            status = "مقبول"
            message = "المعدل التراكمي مقبول. يجب العمل على تحسينه."
        else:
            status = "ضعيف"
            message = "المعدل التراكمي منخفض. يجب رفعه لتجنب الإنذار الأكاديمي."
        
        return {
            "current_gpa": cumulative_gpa,
            "minimum_required": GraduationEligibilityService.MINIMUM_GPA,
            "status": status,
            "message": message,
            "meets_requirement": cumulative_gpa >= GraduationEligibilityService.MINIMUM_GPA
        }

    @staticmethod
    def _get_academic_warnings(student_id):
        """الحصول على الإنذارات الأكاديمية"""
        try:
            active_warnings = AcademicWarnings.query.filter(
                AcademicWarnings.StudentId == student_id,
                AcademicWarnings.Status == "نشط"
            ).all()
            
            return [
                {
                    "id": warning.Id,
                    "type": warning.WarningType,
                    "level": warning.WarningLevel,
                    "description": warning.Description,
                    "issue_date": warning.IssueDate.isoformat() if warning.IssueDate else None,
                    "action_required": warning.ActionRequired,
                    "is_active": warning.Status == "نشط",
                    "semester": warning.Semester
                }
                for warning in active_warnings
            ]
        except Exception as e:
            logger.error(f"Error getting academic warnings: {str(e)}")
            return []

    @staticmethod
    def _determine_graduation_status(credits_analysis, cumulative_gpa, warnings):
        """تحديد حالة أهلية التخرج"""
        # التحقق من الساعات
        credits_complete = credits_analysis["remaining_total"] == 0
        
        # التحقق من المعدل
        gpa_meets_requirement = cumulative_gpa >= GraduationEligibilityService.MINIMUM_GPA
        
        # التحقق من الإنذارات
        has_active_warnings = len([w for w in warnings if w.get("is_active", False)]) > 0
        
        # تحديد الحالة
        if credits_complete and gpa_meets_requirement and not has_active_warnings:
            status = "مؤهل للتخرج"
            message = "تهانينا! أنت مؤهل للتخرج."
            eligible = True
        elif not credits_complete and gpa_meets_requirement and not has_active_warnings:
            remaining = credits_analysis["remaining_total"]
            status = "غير مؤهل - متطلبات ناقصة"
            message = f"يجب إكمال {remaining} ساعة إضافية للتخرج"
            eligible = False
        elif credits_complete and not gpa_meets_requirement and not has_active_warnings:
            status = "غير مؤهل - معدل منخفض"
            message = f"يجب رفع المعدل التراكمي إلى {GraduationEligibilityService.MINIMUM_GPA} على الأقل"
            eligible = False
        elif has_active_warnings:
            status = "مشروط - إنذارات أكاديمية"
            message = "يجب حل الإنذارات الأكاديمية أولاً"
            eligible = False
        else:
            status = "غير مؤهل - متطلبات متعددة"
            message = "يجب إكمال المتطلبات الأكاديمية والمعدل المطلوب"
            eligible = False
        
        return {
            "eligible": eligible,
            "status": status,
            "message": message,
            "completion_percentage": credits_analysis["completion_percentage"],
            "requirements_met": {
                "credits": credits_complete,
                "gpa": gpa_meets_requirement,
                "no_warnings": not has_active_warnings
            }
        }

    @staticmethod
    def _calculate_graduation_planning(credits_analysis, current_semester):
        """حساب التخطيط للتخرج"""
        remaining_credits = credits_analysis["remaining_total"]
        
        if remaining_credits == 0:
            return {
                "semesters_remaining": 0,
                "expected_graduation_date": "مؤهل للتخرج الآن",
                "credits_per_semester": 0,
                "recommended_load": "لا توجد مواد متبقية"
            }
        
        # افتراض أن الطالب يأخذ 15-18 ساعة في الفصل
        average_credits_per_semester = 16
        semesters_remaining = max(1, (remaining_credits + average_credits_per_semester - 1) // average_credits_per_semester)
        
        # حساب التاريخ المتوقع للتخرج (تقريبي)
        current_year = datetime.now().year
        expected_year = current_year + (semesters_remaining // 2)
        expected_semester = "الفصل الأول" if semesters_remaining % 2 == 1 else "الفصل الثاني"
        
        return {
            "semesters_remaining": semesters_remaining,
            "expected_graduation_date": f"{expected_semester} {expected_year}",
            "credits_per_semester": remaining_credits // semesters_remaining if semesters_remaining > 0 else 0,
            "recommended_load": f"يُنصح بأخذ {average_credits_per_semester} ساعة في الفصل"
        }

    @staticmethod
    def _generate_recommendations(graduation_status, credits_analysis, gpa_analysis, remaining_courses):
        """إنشاء التوصيات الأكاديمية"""
        recommendations = []
        
        # توصيات بناءً على حالة التخرج
        if not graduation_status["eligible"]:
            if not graduation_status["requirements_met"]["credits"]:
                remaining_credits = credits_analysis["remaining_total"]
                mandatory_remaining = credits_analysis["mandatory"]["remaining"]
                elective_remaining = credits_analysis["elective"]["remaining"]
                
                if mandatory_remaining > 0:
                    recommendations.append({
                        "type": "أكاديمي",
                        "priority": "عالية",
                        "message": f"يجب إكمال {mandatory_remaining} ساعة إجبارية من أصل {remaining_credits} ساعة متبقية"
                    })
                
                if elective_remaining > 0:
                    recommendations.append({
                        "type": "أكاديمي", 
                        "priority": "متوسطة",
                        "message": f"يجب إكمال {elective_remaining} ساعة اختيارية"
                    })
            
            if not graduation_status["requirements_met"]["gpa"]:
                recommendations.append({
                    "type": "أكاديمي",
                    "priority": "عالية", 
                    "message": f"يجب رفع المعدل التراكمي من {gpa_analysis['current_gpa']} إلى {GraduationEligibilityService.MINIMUM_GPA} على الأقل"
                })
        
        # توصيات للمواد المتاحة
        available_courses = [course for course in remaining_courses if course["availability_status"] == "متاحة للتسجيل"]
        if available_courses:
            mandatory_available = [c for c in available_courses if c["type"] == "إجبارية"]
            if mandatory_available:
                recommendations.append({
                    "type": "تسجيل",
                    "priority": "عالية",
                    "message": f"يوجد {len(mandatory_available)} مادة إجبارية متاحة للتسجيل حالياً"
                })
        
        # توصيات للمواد غير المتاحة
        unavailable_courses = [course for course in remaining_courses if course["availability_status"] != "متاحة للتسجيل"]
        if unavailable_courses:
            recommendations.append({
                "type": "تخطيط",
                "priority": "متوسطة", 
                "message": f"يوجد {len(unavailable_courses)} مادة غير متاحة حالياً - خطط للفصول القادمة"
            })
        
        # توصيات عامة
        if graduation_status["completion_percentage"] > 80:
            recommendations.append({
                "type": "تحفيزي",
                "priority": "منخفضة",
                "message": "أنت قريب من التخرج! استمر في العمل الجيد"
            })
        
        return recommendations

    @staticmethod
    def _calculate_gpa(student_id):
        """حساب المعدل التراكمي الصحيح بناءً على الساعات المعتمدة والدرجات"""
        try:
            # الحصول على بيانات الطالب
            student = Students.query.get(student_id)
            if not student:
                return 0.0
            
            # الحصول على تاريخ المعدل التراكمي
            gpa_history = []
            for i in range(1, student.Semester + 1):
                gpa_field = f'GPA{i}'
                if hasattr(student, gpa_field) and getattr(student, gpa_field) is not None:
                    gpa_history.append(float(getattr(student, gpa_field)))
            
            # حساب المتوسط
            if gpa_history:
                cumulative_gpa = sum(gpa_history) / len(gpa_history)
                return round(cumulative_gpa, 2)
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating GPA: {str(e)}")
            return 0.0


class EnrollmentPeriodService:
    
    @staticmethod
    def create_enrollment_period(semester, start_date, end_date):
        try:
            validation_result = EnrollmentPeriodService._validate_enrollment_period_data(
                semester, start_date, end_date
            )
            
            if not validation_result["is_valid"]:
                return {
                    "success": False,
                    "message": validation_result["message"],
                    "errors": validation_result.get("errors", [])
                }
            
            existing_period = EnrollmentPeriods.query.filter_by(Semester=semester).first()
            if existing_period:
                return {
                    "success": False,
                    "message": f"فترة التسجيل للفصل الدراسي '{semester}' موجودة بالفعل"
                }
            
            overlap_check = EnrollmentPeriodService._check_date_overlap(start_date, end_date)
            if not overlap_check["is_valid"]:
                return {
                    "success": False,
                    "message": overlap_check["message"]
                }
            
            new_period = EnrollmentPeriods(
                Semester=semester,
                StartDate=start_date,
                EndDate=end_date
            )
            
            db.session.add(new_period)
            db.session.commit()
            
            return {
                "success": True,
                "message": "تم إنشاء فترة التسجيل بنجاح",
                "data": {
                    "id": new_period.Id,
                    "semester": new_period.Semester,
                    "start_date": new_period.StartDate.isoformat(),
                    "end_date": new_period.EndDate.isoformat()
                }
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                "success": False,
                "message": f"حدث خطأ أثناء إنشاء فترة التسجيل: {str(e)}"
            }
    
    @staticmethod
    def get_all_enrollment_periods():
        try:
            periods = EnrollmentPeriods.query.order_by(EnrollmentPeriods.StartDate.desc()).all()
            
            periods_data = []
            for period in periods:
                periods_data.append({
                    "id": period.Id,
                    "semester": period.Semester,
                    "start_date": period.StartDate.isoformat(),
                    "end_date": period.EndDate.isoformat(),
                    "status": EnrollmentPeriodService._get_period_status(period)
                })
            
            return {
                "success": True,
                "data": periods_data,
                "message": "تم استرجاع فترات التسجيل بنجاح"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"حدث خطأ أثناء استرجاع فترات التسجيل: {str(e)}"
            }
    
    @staticmethod
    def get_current_enrollment_period():
        try:
            current_date = datetime.now()
            current_period = EnrollmentPeriods.query.filter(
                EnrollmentPeriods.StartDate <= current_date,
                EnrollmentPeriods.EndDate >= current_date
            ).first()
            
            if current_period:
                return {
                    "success": True,
                    "data": {
                        "id": current_period.Id,
                        "semester": current_period.Semester,
                        "start_date": current_period.StartDate.isoformat(),
                        "end_date": current_period.EndDate.isoformat(),
                        "status": "نشطة"
                    },
                    "message": "تم العثور على فترة التسجيل الحالية"
                }
            else:
                return {
                    "success": False,
                    "message": "لا توجد فترة تسجيل نشطة حالياً"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"حدث خطأ أثناء البحث عن فترة التسجيل الحالية: {str(e)}"
            }
    
    @staticmethod
    def _validate_enrollment_period_data(semester, start_date, end_date):
        errors = []
        
        if not semester or not isinstance(semester, str) or len(semester.strip()) == 0:
            errors.append("الفصل الدراسي مطلوب ويجب أن يكون نص غير فارغ")
        elif len(semester.strip()) > 50:
            errors.append("الفصل الدراسي يجب أن يكون أقل من 50 حرف")
        
        if not start_date:
            errors.append("تاريخ بداية التسجيل مطلوب")
        elif not isinstance(start_date, datetime):
            errors.append("تاريخ بداية التسجيل يجب أن يكون من نوع datetime")
        
        if not end_date:
            errors.append("تاريخ نهاية التسجيل مطلوب")
        elif not isinstance(end_date, datetime):
            errors.append("تاريخ نهاية التسجيل يجب أن يكون من نوع datetime")
        
        if start_date and end_date and isinstance(start_date, datetime) and isinstance(end_date, datetime):
            if end_date <= start_date:
                errors.append("تاريخ نهاية التسجيل يجب أن يكون بعد تاريخ البداية")
            
            duration = (end_date - start_date).days
            if duration < 1:
                errors.append("فترة التسجيل يجب أن تكون على الأقل يوم واحد")
            
            if duration > 365:
                errors.append("فترة التسجيل يجب أن تكون أقل من سنة واحدة")
        
        return {
            "is_valid": len(errors) == 0,
            "message": "البيانات صحيحة" if len(errors) == 0 else "توجد أخطاء في البيانات المدخلة",
            "errors": errors
        }
    
    @staticmethod
    def _check_date_overlap(start_date, end_date):
        """التحقق من عدم تداخل التواريخ مع فترات تسجيل أخرى"""
        try:
            overlapping_periods = EnrollmentPeriods.query.filter(
                db.or_(
                    db.and_(
                        EnrollmentPeriods.StartDate <= start_date,
                        EnrollmentPeriods.EndDate >= start_date
                    ),
                    db.and_(
                        EnrollmentPeriods.StartDate <= end_date,
                        EnrollmentPeriods.EndDate >= end_date
                    ),
                 
                    db.and_(
                        EnrollmentPeriods.StartDate >= start_date,
                        EnrollmentPeriods.EndDate <= end_date
                    )
                )
            ).first()
            
            if overlapping_periods:
                return {
                    "is_valid": False,
                    "message": f"التواريخ المحددة تتداخل مع فترة التسجيل للفصل '{overlapping_periods.Semester}'"
                }
            
            return {
                "is_valid": True,
                "message": "التواريخ صحيحة ولا تتداخل مع فترات أخرى"
            }
            
        except Exception as e:
            return {
                "is_valid": False,
                "message": f"حدث خطأ أثناء التحقق من التواريخ: {str(e)}"
            }
    
    @staticmethod
    def _get_period_status(period):
        current_date = datetime.now()
        
        if current_date < period.StartDate:
            return "قادمة"
        elif current_date > period.EndDate:
            return "منتهية"
        else:
            return "نشطة" 

class SmartCourseRecommendationService:
    """خدمة التوصية الذكية للمواد الدراسية"""
    
    def __init__(self):
        self.weights = {
            'content_based': 0.3,
            'academic_performance': 0.25,
            'schedule_optimization': 0.2,
            'prerequisite_analysis': 0.15,
            'gpa_improvement': 0.1
        }
    
    def get_smart_recommendations(self, student_id):
        """الحصول على التوصيات الذكية للطالب"""
        try:
            # جمع بيانات الطالب
            student_data = self._get_enhanced_student_data(student_id)
            if not student_data:
                return {"error": "الطالب غير موجود"}, 404
            
            # تصنيف الطالب أكاديمياً
            academic_status = self._classify_student_academic_status(student_data)
            
            # الحصول على المواد المتاحة
            available_courses = self._get_available_courses(student_data)
            
            # تطبيق خوارزميات التوصية المختلفة
            recommendations = self._generate_categorized_recommendations(
                student_data, available_courses, academic_status
            )
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in smart recommendations: {str(e)}")
            return {"error": str(e)}, 500
    
    def _get_enhanced_student_data(self, student_id):
        """جمع بيانات شاملة عن الطالب"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return None
            
            # الحصول على معلومات القسم من خلال الشعبة
            department_id = None
            if student.DivisionId:
                division = Divisions.query.get(student.DivisionId)
                if division:
                    department_id = division.DepartmentId
            
            # الحصول على المعدل التراكمي الحالي
            current_gpa = self._get_current_gpa(student)
            
            # الحصول على المواد المكتملة والراسب فيها والمسجل فيها حالياً
            completed_courses = self._get_completed_courses(student_id)
            failed_courses = self._get_failed_courses(student_id)
            currently_enrolled_course_ids = self._get_currently_enrolled_courses(student_id)
            
            # تحليل الأداء الأكاديمي
            performance_analysis = self._analyze_academic_performance(student)
            
            # تحليل أنماط الحضور
            attendance_analysis = self._analyze_attendance_patterns(student_id)
            
            return {
                'id': student.Id,
                'name': student.Name,
                'department_id': department_id,
                'division_id': student.DivisionId,
                'current_semester': student.Semester,
                'credits_completed': student.CreditsCompleted,
                'current_gpa': current_gpa,
                'gpa_history': self._get_gpa_history(student),
                'completed_courses': completed_courses,
                'failed_courses': failed_courses,
                'currently_enrolled_course_ids': currently_enrolled_course_ids,
                'performance_analysis': performance_analysis,
                'attendance_analysis': attendance_analysis
            }
            
        except Exception as e:
            logger.error(f"Error getting enhanced student data: {str(e)}")
            return None
    
    def _get_current_gpa(self, student):
        """الحصول على المعدل التراكمي الحالي - متوسط جميع الفصول"""
        try:
            gpa_history = self._get_gpa_history(student)
            if gpa_history:
                return sum(gpa_history) / len(gpa_history)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting current GPA: {str(e)}")
            return 0.0
    
    def _get_gpa_history(self, student):
        """الحصول على تاريخ المعدل التراكمي"""
        try:
            gpa_history = []
            for i in range(1, student.Semester + 1):
                gpa_field = f'GPA{i}'
                if hasattr(student, gpa_field) and getattr(student, gpa_field) is not None:
                    gpa_history.append(float(getattr(student, gpa_field)))
            return gpa_history
        except Exception as e:
            logger.error(f"Error getting GPA history: {str(e)}")
            return []
    
    def _get_completed_courses(self, student_id):
        """الحصول على المواد المكتملة بنجاح"""
        try:
            enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted='مكتملة'
            ).all()
            
            completed_courses = []
            for enrollment in enrollments:
                course = Courses.query.get(enrollment.CourseId)
                if course:
                    # حساب الدرجة الكلية من 150 (30 + 30 + 90)
                    exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                    exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                    final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                    total_grade = exam1_grade + exam2_grade + final_grade
                    
                    completed_courses.append({
                        'id': course.Id,
                        'name': course.Name,
                        'code': course.Code,
                        'credits': course.Credits,
                        'grade': total_grade,  # الدرجة الكلية من 150
                        'exam1_grade': exam1_grade,
                        'exam2_grade': exam2_grade,
                        'final_grade': final_grade,
                        'semester': enrollment.Semester
                    })
            
            return completed_courses
        except Exception as e:
            logger.error(f"Error getting completed courses: {str(e)}")
            return []
    
    def _get_currently_enrolled_courses(self, student_id):
        """الحصول على المواد المسجل فيها حالياً (قيد الدراسة)"""
        try:
            enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted='قيد الدراسة'
            ).all()
            
            currently_enrolled_ids = [enrollment.CourseId for enrollment in enrollments]
            return currently_enrolled_ids
            
        except Exception as e:
            logger.error(f"Error getting currently enrolled courses: {str(e)}")
            return []
    
    def _get_failed_courses(self, student_id):
        """الحصول على المواد الراسب فيها"""
        try:
            enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted='راسب'
            ).all()
            
            failed_courses = []
            for enrollment in enrollments:
                course = Courses.query.get(enrollment.CourseId)
                if course:
                    # التحقق من كون المادة إجبارية
                    is_mandatory = self._is_course_mandatory(course.Id, student_id)
                    
                    # الحصول على معلومات الحصة
                    class_info = self._get_course_class_info(course.Id)
                    
                    failed_courses.append({
                        'id': course.Id,
                        'name': course.Name,
                        'code': course.Code,
                        'description': course.Description,
                        'credits': course.Credits,
                        'semester': course.Semester,
                        'is_mandatory': is_mandatory,
                        'max_seats': course.MaxSeats,
                        'current_enrolled': course.CurrentEnrolledStudents,
                        'professor_name': class_info.get('professor_name'),
                        'day_name': class_info.get('day_name'),
                        'start_time': class_info.get('start_time'),
                        'end_time': class_info.get('end_time'),
                        'location': class_info.get('location')
                    })
            
            return failed_courses
        except Exception as e:
            logger.error(f"Error getting failed courses: {str(e)}")
            return []
    
    def _is_course_mandatory(self, course_id, student_id):
        """التحقق من كون المادة إجبارية للطالب"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return False
            
            course_division = CourseDivisions.query.filter_by(
                CourseId=course_id,
                DivisionId=student.DivisionId,
                IsMandatory=True
            ).first()
            
            return course_division is not None
        except Exception as e:
            logger.error(f"Error checking if course is mandatory: {str(e)}")
            return False
    
    def _classify_student_academic_status(self, student_data):
        """تصنيف الطالب أكاديمياً"""
        try:
            current_gpa = student_data['current_gpa']
            failed_courses_count = len(student_data['failed_courses'])
            gpa_history = student_data['gpa_history']
            
            # تحليل اتجاه المعدل
            gpa_trend = 'stable'
            if len(gpa_history) >= 2:
                if gpa_history[-1] > gpa_history[-2]:
                    gpa_trend = 'improving'
                elif gpa_history[-1] < gpa_history[-2]:
                    gpa_trend = 'declining'
            
            # تصنيف الطالب
            if current_gpa >= 3.5:
                status = 'excellent'
            elif current_gpa >= 3.0:
                status = 'very_good'
            elif current_gpa >= 2.5:
                status = 'good'
            elif current_gpa >= 2.0:
                status = 'acceptable'
            else:
                status = 'at_risk'
            
            # تعديل التصنيف بناءً على عوامل إضافية
            if failed_courses_count > 3:
                status = 'at_risk'
            elif failed_courses_count > 1 and current_gpa < 2.5:
                status = 'needs_attention'
            
            return {
                'status': status,
                'gpa_trend': gpa_trend,
                'risk_factors': {
                    'low_gpa': current_gpa < 2.0,
                    'multiple_failures': failed_courses_count > 2,
                    'declining_trend': gpa_trend == 'declining'
                }
            }
            
        except Exception as e:
            logger.error(f"Error classifying student: {str(e)}")
            return {'status': 'unknown', 'gpa_trend': 'stable', 'risk_factors': {}}
    
    def _analyze_academic_performance(self, student):
        """تحليل الأداء الأكاديمي للطالب"""
        try:
            # تحليل الأداء في المواد المختلفة
            enrollments = Enrollments.query.filter_by(
                StudentId=student.Id,
                IsCompleted='ناجح'
            ).all()
            
            subject_performance = {}
            total_credits = 0
            weighted_grade_sum = 0
            
            for enrollment in enrollments:
                course = Courses.query.get(enrollment.CourseId)
                if course:
                    # حساب الدرجة الكلية من 150 (30 + 30 + 90)
                    exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                    exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                    final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                    total_grade = exam1_grade + exam2_grade + final_grade
                    
                    credits = course.Credits
                    
                    # تصنيف المادة حسب النوع - سيتم إزالة هذا لاحقاً
                    subject_type = 'general'  # تبسيط التصنيف
                    
                    if subject_type not in subject_performance:
                        subject_performance[subject_type] = {
                            'total_grades': 0,
                            'total_credits': 0,
                            'course_count': 0
                        }
                    
                    subject_performance[subject_type]['total_grades'] += total_grade * credits
                    subject_performance[subject_type]['total_credits'] += credits
                    subject_performance[subject_type]['course_count'] += 1
                    
                    total_credits += credits
                    weighted_grade_sum += total_grade * credits
            
            # حساب المتوسط لكل نوع مادة
            for subject_type in subject_performance:
                perf = subject_performance[subject_type]
                if perf['total_credits'] > 0:
                    perf['average_grade'] = perf['total_grades'] / perf['total_credits']
                else:
                    perf['average_grade'] = 0
            
            overall_average = weighted_grade_sum / total_credits if total_credits > 0 else 0
            
            return {
                'subject_performance': subject_performance,
                'overall_average': overall_average,
                'strengths': [],  # سيتم تبسيط هذا
                'weaknesses': []  # سيتم تبسيط هذا
            }
            
        except Exception as e:
            logger.error(f"Error analyzing academic performance: {str(e)}")
            return {}
    
    def _analyze_attendance_patterns(self, student_id):
        """تحليل أنماط الحضور"""
        try:
            # الحصول على بيانات الحضور
            attendance_records = Attendances.query.filter_by(StudentId=student_id).all()
            
            if not attendance_records:
                return {'attendance_rate': 100, 'pattern': 'no_data'}
            
            total_sessions = len(attendance_records)
            attended_sessions = sum(1 for record in attendance_records if record.Status)
            attendance_rate = (attended_sessions / total_sessions) * 100
            
            # تحديد نمط الحضور
            if attendance_rate >= 90:
                pattern = 'excellent'
            elif attendance_rate >= 80:
                pattern = 'good'
            elif attendance_rate >= 70:
                pattern = 'acceptable'
            else:
                pattern = 'poor'
            
            return {
                'attendance_rate': attendance_rate,
                'pattern': pattern,
                'total_sessions': total_sessions,
                'attended_sessions': attended_sessions
            }
            
        except Exception as e:
            logger.error(f"Error analyzing attendance: {str(e)}")
            return {'attendance_rate': 100, 'pattern': 'no_data'}
    
    def _get_available_courses(self, student_data):
        """الحصول على المواد المتاحة للطالب مع معلومات الأستاذ والجدول"""
        try:
            # الحصول على المواد المتاحة للقسم والشعبة
            available_courses = db.session.query(Courses).join(
                CourseDivisions, Courses.Id == CourseDivisions.CourseId
            ).filter(
                CourseDivisions.DivisionId == student_data['division_id'],
                Courses.Status == 'متاح'
            ).all()
            
            # فلترة المواد المكتملة بالفعل والمسجل فيها حالياً
            completed_course_ids = [course['id'] for course in student_data['completed_courses']]
            currently_enrolled_course_ids = student_data.get('currently_enrolled_course_ids', [])
            excluded_course_ids = completed_course_ids + currently_enrolled_course_ids
            
            filtered_courses = []
            for course in available_courses:
                if course.Id not in excluded_course_ids:
                    # التحقق من المتطلبات السابقة
                    prerequisites_met = self._check_prerequisites(course.Id, completed_course_ids)
                    
                    if prerequisites_met:
                        course_division = CourseDivisions.query.filter_by(
                            CourseId=course.Id,
                            DivisionId=student_data['division_id']
                        ).first()
                        
                        # الحصول على معلومات الفصل والأستاذ
                        class_info = self._get_course_class_info(course.Id)
                        
                        filtered_courses.append({
                            'id': course.Id,
                            'name': course.Name,
                            'code': course.Code,
                            'description': course.Description,
                            'credits': course.Credits,
                            'semester': course.Semester,
                            'is_mandatory': course_division.IsMandatory if course_division else False,
                            'max_seats': course.MaxSeats,
                            'current_enrolled': course.CurrentEnrolledStudents,
                            'professor_name': class_info.get('professor_name', 'غير محدد'),
                            'day': class_info.get('day', 'غير محدد'),
                            'day_name': class_info.get('day_name', 'غير محدد'),
                            'start_time': class_info.get('start_time', 'غير محدد'),
                            'end_time': class_info.get('end_time', 'غير محدد'),
                            'location': class_info.get('location', 'غير محدد')
                        })
            
            return filtered_courses
            
        except Exception as e:
            logger.error(f"Error getting available courses: {str(e)}")
            return []
    
    def _get_course_class_info(self, course_id):
        """الحصول على معلومات الفصل والأستاذ للمادة"""
        try:
            class_session = Classes.query.filter_by(CourseId=course_id).first()
            
            if not class_session:
                return {}
            
            professor = Professors.query.get(class_session.ProfessorId)
            
            # تحويل رقم اليوم إلى اسم اليوم
            day_names = {
                '1': 'السبت',
                '2': 'الأحد', 
                '3': 'الاثنين',
                '4': 'الثلاثاء',
                '5': 'الأربعاء',
                '6': 'الخميس',
                '7': 'الجمعة'
            }
            
            return {
                'professor_name': professor.FullName if professor else 'غير محدد',
                'day': class_session.Day,
                'day_name': day_names.get(str(class_session.Day), f'يوم {class_session.Day}'),
                'start_time': str(class_session.StartTime) if class_session.StartTime else 'غير محدد',
                'end_time': str(class_session.EndTime) if class_session.EndTime else 'غير محدد',
                'location': class_session.Location or 'غير محدد'
            }
            
        except Exception as e:
            logger.error(f"Error getting course class info: {str(e)}")
            return {}
    
    def _check_prerequisites(self, course_id, completed_course_ids):
        """التحقق من المتطلبات السابقة للمادة"""
        try:
            prerequisites = CoursePrerequisites.query.filter_by(CourseId=course_id).all()
            
            for prereq in prerequisites:
                if prereq.PrerequisiteCourseId not in completed_course_ids:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking prerequisites: {str(e)}")
            return True
    
    def _generate_categorized_recommendations(self, student_data, available_courses, academic_status):
        """توليد التوصيات المصنفة"""
        try:
            current_semester = student_data['current_semester']
            
            # تصنيف المواد حسب النوع والترم
            current_semester_mandatory = []
            elective_courses = []  # المواد الاختيارية الأصلية فقط
            
            for course in available_courses:
                if course['is_mandatory']:
                    if course['semester'] == current_semester:
                        # مواد إجبارية للترم الحالي
                        current_semester_mandatory.append(course)
                    # المواد الإجبارية من الترمات السابقة والقادمة ستكون لها APIs منفصلة
                else:
                    # المواد الاختيارية الأصلية فقط
                    elective_courses.append(course)
            
            failed_mandatory_courses = [course for course in student_data['failed_courses'] if course['is_mandatory']]
            
            # توليد التوصيات لكل فئة
            recommendations = {
                'mandatory_courses': self._recommend_mandatory_courses(
                    current_semester_mandatory, student_data, academic_status
                ),
                'failed_courses_retry': self._recommend_failed_courses_retry(
                    failed_mandatory_courses, student_data, academic_status
                ),
                'gpa_improvement_courses': self._recommend_gpa_improvement_courses(
                    elective_courses, student_data, academic_status
                ),
                'elective_courses': self._recommend_elective_courses(
                    elective_courses, student_data, academic_status
                ),
                'academic_status': academic_status,
                'summary': self._generate_recommendation_summary(student_data, academic_status)
            }
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating categorized recommendations: {str(e)}")
            return {}
    
    def _recommend_mandatory_courses(self, mandatory_courses, student_data, academic_status):
        """توصية المواد الإجبارية للترم الحالي"""
        try:
            recommendations = []
            current_semester = student_data['current_semester']
            
            for course in mandatory_courses:
                # حساب درجة الأولوية
                priority_score = self._calculate_mandatory_priority(course, student_data)
                
                # حساب درجة الصعوبة المتوقعة
                difficulty_score = self._estimate_course_difficulty(course, student_data)
                
                # تحديد التوصية
                recommendation_reason = self._get_mandatory_recommendation_reason(
                    course, student_data, priority_score, difficulty_score, current_semester
                )
                
                recommendations.append({
                    'course': course,
                    'priority_score': priority_score,
                    'difficulty_score': difficulty_score,
                    'recommendation_reason': recommendation_reason,
                    'suggested_semester': current_semester  # الترم الحالي
                })
            
            # ترتيب حسب الأولوية
            recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
            
            return recommendations  # إرجاع جميع التوصيات للترم الحالي
            
        except Exception as e:
            logger.error(f"Error recommending mandatory courses: {str(e)}")
            return []
    
    def _recommend_failed_courses_retry(self, failed_courses, student_data, academic_status):
        """توصية إعادة المواد الراسب فيها"""
        try:
            # إذا لم توجد مواد راسب فيها
            if not failed_courses:
                return {
                    'message': 'لا توجد مواد راسب فيها تحتاج إلى إعادة',
                    'current_gpa': student_data.get('current_gpa', 0),
                    'status': academic_status['status'],
                    'recommendation': 'استمر في الأداء الجيد والتركيز على المواد الإجبارية والاختيارية',
                    'courses': []
                }
            
            recommendations = []
            
            for course in failed_courses:
                # حساب الأولوية والصعوبة
                priority_score = self._calculate_mandatory_priority(course, student_data)
                difficulty_score = self._estimate_course_difficulty(course, student_data)
                
                # تحديد الترم المقترح
                suggested_semester = self._suggest_optimal_semester(course, student_data, academic_status)
                
                # سبب التوصية
                recommendation_reason = self._get_mandatory_recommendation_reason(
                    course, student_data, priority_score, difficulty_score, student_data['current_semester']
                )
                
                recommendations.append({
                    'course': course,
                    'priority_score': priority_score,
                    'difficulty_score': difficulty_score,
                    'recommendation_reason': recommendation_reason,
                    'suggested_semester': suggested_semester
                })
            
            # ترتيب حسب الأولوية
            recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
            
            return {
                'message': f'يوجد {len(recommendations)} مادة راسب فيها تحتاج إلى إعادة',
                'current_gpa': student_data.get('current_gpa', 0),
                'status': academic_status['status'],
                'recommendation': 'يُنصح بإعادة هذه المواد في أقرب وقت ممكن لتحسين المعدل التراكمي',
                'courses': recommendations
            }
            
        except Exception as e:
            logger.error(f"Error recommending failed courses retry: {str(e)}")
            return {
                'message': 'حدث خطأ أثناء البحث عن المواد الراسب فيها',
                'courses': []
            }
    
    def _recommend_gpa_improvement_courses(self, elective_courses, student_data, academic_status):
        """توصية مواد لتحسين المعدل التراكمي"""
        try:
            current_gpa = student_data.get('current_gpa', 0)
            
            # إذا كان المعدل جيد، إرجاع رسالة بدلاً من قائمة فارغة
            if academic_status['status'] not in ['at_risk', 'needs_attention', 'acceptable']:
                return {
                    'message': f'معدلك التراكمي ممتاز ({current_gpa:.2f}) ولا يحتاج إلى تحسين',
                    'current_gpa': current_gpa,
                    'status': academic_status['status'],
                    'recommendation': 'استمر في الأداء الممتاز والتركيز على المواد الإجبارية والاختيارية المفيدة لتخصصك',
                    'courses': []
                }
            
            recommendations = []
            
            for course in elective_courses:
                # حساب احتمالية الحصول على درجة عالية
                high_grade_probability = self._calculate_high_grade_probability(course, student_data)
                
                # تقييم سهولة المادة
                ease_score = self._calculate_course_ease_score(course, student_data)
                
                # حساب تأثير المادة على المعدل
                gpa_impact = self._calculate_gpa_impact(course, student_data)
                
                # شروط مرنة حسب حالة الطالب
                if academic_status['status'] == 'at_risk':
                    # شروط أكثر مرونة للطلاب المتعثرين
                    min_ease_score = 0.4
                    min_probability = 0.5
                else:
                    # شروط عادية للطلاب الآخرين
                    min_ease_score = 0.6
                    min_probability = 0.7
                
                if high_grade_probability > min_probability and ease_score > min_ease_score:
                    recommendations.append({
                        'course': course,
                        'high_grade_probability': high_grade_probability,
                        'ease_score': ease_score,
                        'gpa_impact': gpa_impact,
                        'recommendation_reason': f"مادة مناسبة مع احتمالية {high_grade_probability*100:.0f}% للحصول على درجة جيدة (سهولة: {ease_score*100:.0f}%)"
                    })
            
            # ترتيب حسب التأثير على المعدل
            recommendations.sort(key=lambda x: x['gpa_impact'], reverse=True)
            
            # إذا لم توجد مواد مناسبة
            if not recommendations:
                return {
                    'message': f'معدلك التراكمي ({current_gpa:.2f}) يحتاج تحسين لكن لا توجد مواد اختيارية سهلة متاحة حالياً',
                    'current_gpa': current_gpa,
                    'status': academic_status['status'],
                    'recommendation': 'ركز على إعادة المواد الراسب فيها أو أخذ المواد الإجبارية بعناية أكبر',
                    'courses': []
                }
            
            return {
                'message': f'تم العثور على {len(recommendations)} مادة لتحسين معدلك التراكمي ({current_gpa:.2f})',
                'current_gpa': current_gpa,
                'status': academic_status['status'],
                'courses': recommendations
            }
            
        except Exception as e:
            logger.error(f"Error recommending GPA improvement courses: {str(e)}")
            return {
                'message': 'حدث خطأ أثناء البحث عن مواد تحسين المعدل',
                'courses': []
            }
    
    def _recommend_elective_courses(self, elective_courses, student_data, academic_status):
        """توصية المواد الاختيارية الأصلية فقط"""
        try:
            recommendations = []
            
            for course in elective_courses:
                # التأكد من أن المادة اختيارية أصلية فقط
                if not course['is_mandatory']:
                    # حساب التشابه مع المواد المكتملة
                    content_similarity = self._calculate_content_similarity(course, student_data)
                    
                    # تقييم التوافق مع نقاط القوة
                    strength_alignment = self._calculate_strength_alignment(course, student_data)
                    
                    # تقييم الفائدة المهنية
                    career_relevance = self._calculate_career_relevance(course, student_data)
                    
                    # حساب النتيجة الإجمالية
                    overall_score = (
                        content_similarity * 0.3 +
                        strength_alignment * 0.4 +
                        career_relevance * 0.3
                    )
                    
                    recommendations.append({
                        'course': course,
                        'content_similarity': content_similarity,
                        'strength_alignment': strength_alignment,
                        'career_relevance': career_relevance,
                        'overall_score': overall_score,
                        'recommendation_reason': self._generate_elective_reason(
                            course, content_similarity, strength_alignment, career_relevance
                        ),
                        'course_type': 'elective'
                    })
            
            # ترتيب حسب النتيجة الإجمالية
            recommendations.sort(key=lambda x: x['overall_score'], reverse=True)
            
            return recommendations 
            
        except Exception as e:
            logger.error(f"Error recommending elective courses: {str(e)}")
            return []
    
    # Helper methods for calculations
    def _calculate_mandatory_priority(self, course, student_data):
        """حساب أولوية المادة الإجبارية"""
        try:
            priority = 0.5  # أساسي
            
            # زيادة الأولوية إذا كانت متطلب لمواد أخرى
            dependent_courses = CoursePrerequisites.query.filter_by(
                PrerequisiteCourseId=course['id']
            ).count()
            priority += dependent_courses * 0.1
            
            # زيادة الأولوية للمواد في الفصول المتقدمة
            if student_data['current_semester'] >= course['semester']:
                priority += 0.3
            
            return min(priority, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating mandatory priority: {str(e)}")
            return 0.5
    
    def _estimate_course_difficulty(self, course, student_data):
        """تقدير صعوبة المادة"""
        try:
            # حساب متوسط الدرجات الكلية للطلاب في هذه المادة (من 150)
            enrollments = Enrollments.query.filter(
                Enrollments.CourseId == course['id'],
                or_(
                    Enrollments.Exam1Grade.isnot(None),
                    Enrollments.Exam2Grade.isnot(None), 
                    Enrollments.Grade.isnot(None)
                )
            ).all()
            
            if enrollments:
                total_grades = []
                for enrollment in enrollments:
                    exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                    exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                    final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                    total_grade = exam1_grade + exam2_grade + final_grade
                    total_grades.append(total_grade)
                
                avg_grade = sum(total_grades) / len(total_grades)
                # كلما قل المتوسط، زادت الصعوبة (الدرجة الكلية من 150)
                difficulty = 1.0 - (avg_grade / 150.0)
            else:
                difficulty = 0.5  # متوسط افتراضي
            
            return max(0.0, min(1.0, difficulty))  # التأكد من أن القيمة بين 0 و 1
            
        except Exception as e:
            logger.error(f"Error estimating course difficulty: {str(e)}")
            return 0.5
    
    def _calculate_content_similarity(self, course, student_data):
        """حساب التشابه في المحتوى"""
        try:
            if not student_data['completed_courses']:
                return 0.5
            
            # استخدام TF-IDF لحساب التشابه
            course_desc = course.get('description', '')
            completed_descs = [c['name'] for c in student_data['completed_courses']]
            
            if not course_desc or not any(completed_descs):
                return 0.5
            
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform([course_desc] + completed_descs)
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
            
            return float(np.mean(similarity))
            
        except Exception as e:
            logger.error(f"Error calculating content similarity: {str(e)}")
            return 0.5
    
    def _calculate_strength_alignment(self, course, student_data):
        """حساب التوافق مع نقاط القوة - مبسط"""
        try:
            # بما أننا أزلنا التصنيف، سنعتمد على المعدل العام للطالب
            current_gpa = student_data.get('current_gpa', 0)
            
            if current_gpa >= 3.5:
                return 0.9  # طالب ممتاز
            elif current_gpa >= 3.0:
                return 0.8  # طالب جيد جداً
            elif current_gpa >= 2.5:
                return 0.7  # طالب جيد
            else:
                return 0.6  # طالب متوسط
                
        except Exception as e:
            logger.error(f"Error calculating strength alignment: {str(e)}")
            return 0.6
    
    def _calculate_career_relevance(self, course, student_data):
        """حساب الصلة بالمسار المهني"""
        # هذا يمكن تطويره لاحقاً بناءً على بيانات سوق العمل
        return 0.7
    
    def _generate_recommendation_summary(self, student_data, academic_status):
        """توليد ملخص التوصيات"""
        try:
            current_semester = student_data['current_semester']
            
            summary = {
                'student_name': student_data['name'],
                'current_semester': current_semester,
                'current_gpa': student_data['current_gpa'],
                'academic_status': academic_status['status'],
                'total_credits_completed': student_data['credits_completed'],
                'failed_courses_count': len(student_data['failed_courses']),
                'api_structure': {
                    'mandatory_current_semester': f'المواد الإجبارية للترم {current_semester} الحالي فقط',
                    'missed_mandatory_api': 'API منفصل للمواد الإجبارية من الترمات السابقة المفقودة',
                    'future_mandatory_api': 'API منفصل للمواد الإجبارية من الترمات القادمة',
                    'failed_retry': 'المواد الإجبارية المطلوب إعادتها',
                    'gpa_improvement': 'مواد اختيارية لتحسين المعدل التراكمي',
                    'elective_pure': 'المواد الاختيارية الأصلية فقط'
                },
                'elective_section_explanation': {
                    'missed_mandatory': 'مواد إجبارية من ترمات سابقة لم يتم أخذها - أولوية عالية جداً',
                    'future_mandatory': 'مواد إجبارية من ترمات قادمة - يمكن أخذها مبكراً',
                    'true_elective': 'مواد اختيارية أصلية - حسب الاهتمام والتخصص'
                },
                'note': f'قسم "المواد الاختيارية" يحتوي على مزيج من المواد الاختيارية الأصلية والمواد الإجبارية المفقودة أو المستقبلية مرتبة حسب الأولوية.'
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return {}
    
    # Additional helper methods
    def _get_mandatory_recommendation_reason(self, course, student_data, priority_score, difficulty_score, current_semester):
        """تحديد سبب توصية المادة الإجبارية"""
        reasons = []
        
        if priority_score > 0.8:
            reasons.append("أولوية عالية للتخرج")
        if difficulty_score < 0.3:
            reasons.append("مادة سهلة نسبياً")
        elif difficulty_score > 0.7:
            reasons.append("مادة صعبة - يُنصح بالتحضير الجيد")
        
        return " - ".join(reasons) if reasons else f"مادة إجبارية في الخطة الدراسية - الترم {current_semester}"
    
    def _suggest_optimal_semester(self, course, student_data, academic_status):
        """اقتراح الفصل الأمثل لأخذ المادة"""
        current_semester = student_data['current_semester']
        
        if academic_status['status'] == 'at_risk':
            return current_semester + 1  # تأجيل للفصل القادم
        else:
            return current_semester  # الفصل الحالي
    
    def _calculate_high_grade_probability(self, course, student_data):
        """حساب احتمالية الحصول على درجة عالية - مبسط"""
        try:
            # حساب بناءً على الأداء السابق العام
            current_gpa = student_data.get('current_gpa', 0)
            
            if current_gpa >= 3.5:
                return 0.85
            elif current_gpa >= 3.0:
                return 0.75
            elif current_gpa >= 2.5:
                return 0.65
            else:
                return 0.55
                
        except Exception as e:
            logger.error(f"Error calculating high grade probability: {str(e)}")
            return 0.65
    
    def _calculate_course_ease_score(self, course, student_data):
        """حساب درجة سهولة المادة"""
        # حساب بناءً على متوسط درجات الطلاب
        difficulty = self._estimate_course_difficulty(course, student_data)
        return 1.0 - difficulty
    
    def _calculate_gpa_impact(self, course, student_data):
        """حساب تأثير المادة على المعدل التراكمي"""
        credits = course['credits']
        total_credits = student_data['credits_completed']
        
        # كلما زادت الساعات، زاد التأثير
        impact = credits / (total_credits + credits) if total_credits > 0 else 0.1
        return impact
    
    def _generate_elective_reason(self, course, content_similarity, strength_alignment, career_relevance):
        """توليد سبب توصية المادة الاختيارية"""
        reasons = []
        
        if content_similarity > 0.7:
            reasons.append("تشابه كبير مع المواد السابقة")
        if strength_alignment > 0.8:
            reasons.append("تتوافق مع نقاط قوتك")
        if career_relevance > 0.7:
            reasons.append("مفيدة للمسار المهني")
        
        return " - ".join(reasons) if reasons else "مادة اختيارية مناسبة"
    
    def _calculate_student_readiness(self, course, student_data):
        """حساب مدى استعداد الطالب لأخذ مادة من ترم مستقبلي"""
        try:
            readiness_score = 0.0
            
            # عامل المعدل التراكمي (40%)
            current_gpa = student_data.get('current_gpa', 0)
            if current_gpa >= 3.5:
                gpa_factor = 1.0
            elif current_gpa >= 3.0:
                gpa_factor = 0.8
            elif current_gpa >= 2.5:
                gpa_factor = 0.6
            else:
                gpa_factor = 0.4
            
            readiness_score += gpa_factor * 0.4
            
            # عامل المتطلبات السابقة (30%)
            completed_course_ids = [course['id'] for course in student_data['completed_courses']]
            prerequisites = CoursePrerequisites.query.filter_by(CourseId=course['id']).all()
            
            if prerequisites:
                met_prerequisites = sum(1 for prereq in prerequisites 
                                     if prereq.PrerequisiteCourseId in completed_course_ids)
                prereq_factor = met_prerequisites / len(prerequisites)
            else:
                prereq_factor = 1.0  # لا توجد متطلبات سابقة
            
            readiness_score += prereq_factor * 0.3
            
            # عامل الأداء في المواد المشابهة (20%)
            similar_performance = self._calculate_similar_courses_performance(course, student_data)
            readiness_score += similar_performance * 0.2
            
            # عامل الحالة الأكاديمية (10%)
            academic_status = student_data.get('performance_analysis', {})
            if current_gpa >= 3.0 and len(student_data.get('failed_courses', [])) == 0:
                status_factor = 1.0
            elif current_gpa >= 2.5:
                status_factor = 0.7
            else:
                status_factor = 0.4
            
            readiness_score += status_factor * 0.1
            
            return min(readiness_score, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating student readiness: {str(e)}")
            return 0.5
    
    def _calculate_similar_courses_performance(self, course, student_data):
        """حساب الأداء في المواد المشابهة"""
        try:
            completed_courses = student_data.get('completed_courses', [])
            if not completed_courses:
                return 0.5
            
            # حساب متوسط الدرجات في المواد المكتملة
            total_grades = sum(course['grade'] for course in completed_courses)
            avg_grade = total_grades / len(completed_courses)
            
            # تحويل إلى نسبة من 1 (الدرجة الكلية من 150)
            performance_ratio = avg_grade / 150.0
            
            return min(performance_ratio, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating similar courses performance: {str(e)}")
            return 0.5 




class CourseEnrollmentService:
    """خدمة تسجيل المواد مع جميع القواعد والتحققات المطلوبة"""
    
    @staticmethod
    def enroll_student_in_course(student_id, course_id):
        """تسجيل طالب في مادة واحدة مع جميع التحققات المطلوبة"""
        try:
            # 1. التحقق من فترة التسجيل
            enrollment_check = CourseEnrollmentService._check_enrollment_period()
            if not enrollment_check["is_active"]:
                return {
                    "success": False,
                    "message": enrollment_check["message"]
                }
            
            # 2. التحقق من وجود الطالب
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود"
                }
            
            # 3. التحقق من وجود المادة
            course = Courses.query.get(course_id)
            if not course:
                return {
                    "success": False,
                    "message": "المادة غير موجودة"
                }
            
            # 4. الحصول على الفصل الدراسي الحالي
            current_semester = CourseEnrollmentService._get_current_semester()
            
            # 5. التحقق من عدم وجود تسجيل سابق للمادة
            existing_enrollment = Enrollments.query.filter_by(
                StudentId=student_id,
                CourseId=course_id
            ).filter(
                Enrollments.IsCompleted.in_(["قيد الدراسة", "مكتملة"])
            ).first()
            
            if existing_enrollment:
                if existing_enrollment.IsCompleted == "قيد الدراسة":
                    return {
                        "success": False,
                        "message": f"الطالب مسجل بالفعل في هذه المادة ({course.Name}) وهي قيد الدراسة حالياً"
                    }
                elif existing_enrollment.IsCompleted == "مكتملة":
                    return {
                        "success": False,
                        "message": f"الطالب أكمل هذه المادة ({course.Name}) مسبقاً ولا يمكن إعادة تسجيلها"
                    }
            
            # 6. التحقق من الساعات المسموحة للطالب
            credit_check = CourseEnrollmentService._check_credit_limit(student, course, current_semester)
            if not credit_check["allowed"]:
                return {
                    "success": False,
                    "message": credit_check["message"]
                }
            
            # 7. التحقق من أن المادة متاحة للطالب (من التوصيات)
            availability_check = CourseEnrollmentService._check_course_availability(student_id, course_id)
            if not availability_check["available"]:
                return {
                    "success": False,
                    "message": availability_check["message"]
                }
            
            # 8. إنشاء التسجيل الجديد
            # تحقق إضافي للأمان قبل إنشاء التسجيل
            final_check = Enrollments.query.filter_by(
                StudentId=student_id,
                CourseId=course_id,
                IsCompleted="قيد الدراسة"
            ).first()
            
            if final_check:
                return {
                    "success": False,
                    "message": f"خطأ: تم اكتشاف تسجيل مكرر للمادة ({course.Name})"
                }
            
            new_enrollment = Enrollments(
                StudentId=student_id,
                CourseId=course_id,
                Semester=current_semester,
                NumberOFSemster=student.Semester,  # رقم الترم الحالي للطالب
                AddedEnrollmentDate=datetime.now().date(),
                IsCompleted="قيد الدراسة",
                Exam1Grade=None,
                Exam2Grade=None,
                Grade=None
            )
            
            db.session.add(new_enrollment)
            
            # 9. تحديث عدد الطلاب المسجلين في المادة
            if hasattr(course, 'CurrentEnrolledStudents'):
                course.CurrentEnrolledStudents = (course.CurrentEnrolledStudents or 0) + 1
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم تسجيل الطالب في مادة {course.Name} بنجاح",
                "data": {
                    "enrollment_id": new_enrollment.Id,
                    "course_name": course.Name,
                    "course_code": course.Code,
                    "credits": course.Credits,
                    "semester": current_semester,
                    "enrollment_date": new_enrollment.AddedEnrollmentDate.isoformat()
                }
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in enroll_student_in_course: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ أثناء التسجيل: {str(e)}"
            }
    
    @staticmethod
    def cancel_enrollment(enrollment_id):
        """إلغاء تسجيل مادة (حذف مؤقت)"""
        try:
            # 1. البحث عن التسجيل
            enrollment = Enrollments.query.get(enrollment_id)
            if not enrollment:
                return {
                    "success": False,
                    "message": "التسجيل غير موجود"
                }
            
            # 2. التحقق من أن التسجيل قيد الدراسة
            if enrollment.IsCompleted != "قيد الدراسة":
                return {
                    "success": False,
                    "message": f"لا يمكن إلغاء هذا التسجيل. الحالة الحالية: {enrollment.IsCompleted}"
                }
            
            # 3. الحصول على بيانات المادة
            course = Courses.query.get(enrollment.CourseId)
            
            # 4. تحديث بيانات التسجيل
            enrollment.DeletedEnrollmentDate = datetime.now().date()
            enrollment.IsCompleted = "ملغاة"
            
            # 5. تحديث عدد الطلاب المسجلين في المادة
            if course and hasattr(course, 'CurrentEnrolledStudents') and course.CurrentEnrolledStudents > 0:
                course.CurrentEnrolledStudents -= 1
            
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم إلغاء تسجيل مادة {course.Name if course else 'غير محدد'} بنجاح",
                "data": {
                    "enrollment_id": enrollment_id,
                    "course_name": course.Name if course else "غير محدد",
                    "course_code": course.Code if course else "غير محدد",
                    "cancellation_date": enrollment.DeletedEnrollmentDate.isoformat()
                }
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in cancel_enrollment: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ أثناء إلغاء التسجيل: {str(e)}"
            }
    
    @staticmethod
    def hard_delete_enrollment(enrollment_id):
        """حذف نهائي للتسجيل (للإدارة فقط)"""
        try:
            # 1. البحث عن التسجيل
            enrollment = Enrollments.query.get(enrollment_id)
            if not enrollment:
                return {
                    "success": False,
                    "message": "التسجيل غير موجود"
                }
            
            # 2. الحصول على بيانات المادة قبل الحذف
            course = Courses.query.get(enrollment.CourseId)
            course_name = course.Name if course else "غير محدد"
            course_code = course.Code if course else "غير محدد"
            
            # 3. تحديث عدد الطلاب المسجلين إذا كان التسجيل نشطاً
            if (enrollment.IsCompleted == "قيد الدراسة" and 
                course and hasattr(course, 'CurrentEnrolledStudents') and 
                course.CurrentEnrolledStudents > 0):
                course.CurrentEnrolledStudents -= 1
            
            # 4. حذف التسجيل نهائياً
            db.session.delete(enrollment)
            db.session.commit()
            
            return {
                "success": True,
                "message": f"تم حذف تسجيل مادة {course_name} نهائياً",
                "data": {
                    "enrollment_id": enrollment_id,
                    "course_name": course_name,
                    "course_code": course_code,
                    "deletion_date": datetime.now().date().isoformat()
                }
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error in hard_delete_enrollment: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ أثناء الحذف النهائي: {str(e)}"
            }
    
    @staticmethod
    def get_student_enrollments(student_id):
        """الحصول على جميع تسجيلات الطالب في الفصل الحالي"""
        try:
            # 1. التحقق من وجود الطالب
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود"
                }
            
            # 2. الحصول على الفصل الدراسي الحالي
            current_semester = CourseEnrollmentService._get_current_semester()
            
            # 3. الحصول على جميع التسجيلات للطالب في الفصل الحالي
            enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                Semester=current_semester
            ).all()
            
            # 4. تصنيف التسجيلات
            active_enrollments = []
            cancelled_enrollments = []
            total_credits = 0
            
            for enrollment in enrollments:
                course = Courses.query.get(enrollment.CourseId)
                
                enrollment_data = {
                    "enrollment_id": enrollment.Id,
                    "course_id": enrollment.CourseId,
                    "course_name": course.Name if course else "غير محدد",
                    "course_code": course.Code if course else "غير محدد",
                    "credits": course.Credits if course else 0,
                    "enrollment_date": enrollment.AddedEnrollmentDate.isoformat() if enrollment.AddedEnrollmentDate else None,
                    "status": enrollment.IsCompleted
                }
                
                if enrollment.IsCompleted == "قيد الدراسة":
                    active_enrollments.append(enrollment_data)
                    total_credits += course.Credits if course else 0
                else:
                    enrollment_data["cancellation_date"] = enrollment.DeletedEnrollmentDate.isoformat() if enrollment.DeletedEnrollmentDate else None
                    cancelled_enrollments.append(enrollment_data)
            
            # 5. حساب الحد الأقصى للساعات المسموحة
            average_gpa = CourseEnrollmentService._calculate_average_gpa(student)
            max_credits = 18 if average_gpa and average_gpa >= 2.0 else 10
            
            return {
                "success": True,
                "message": "تم استرجاع تسجيلات الطالب بنجاح",
                "data": {
                    "student_id": student_id,
                    "student_name": student.Name,
                    "semester": current_semester,
                    "active_enrollments": active_enrollments,
                    "cancelled_enrollments": cancelled_enrollments,
                    "total_active_credits": total_credits,
                    "max_allowed_credits": max_credits,
                    "remaining_credits": max_credits - total_credits
                }
            }
            
        except Exception as e:
            logger.error(f"Error in get_student_enrollments: {str(e)}")
            return {
                "success": False,
                "message": f"حدث خطأ أثناء استرجاع التسجيلات: {str(e)}"
            }
    
    @staticmethod
    def _calculate_average_gpa(student):
        """حساب متوسط GPA لجميع الترمات مع حالة استثنائية للطلاب الجدد"""
        try:
            # حالة استثنائية: الطلاب في الترم الأول فقط يُسمح لهم بـ 18 ساعة
            if hasattr(student, 'Semester') and student.Semester == 1:
                return 2.0  # إرجاع قيمة تسمح بـ 18 ساعة
            
            gpa_values = []
            
            # جمع جميع قيم GPA من الترمات المختلفة
            for i in range(1, 9):  # GPA1 إلى GPA8
                gpa_attr = f'GPA{i}'
                if hasattr(student, gpa_attr):
                    gpa_value = getattr(student, gpa_attr)
                    if gpa_value is not None and gpa_value > 0:
                        gpa_values.append(float(gpa_value))
            
            # حساب المتوسط
            if gpa_values:
                return sum(gpa_values) / len(gpa_values)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in _calculate_average_gpa: {str(e)}")
            # في حالة الخطأ، إذا كان طالب في الترم الأول فقط نسمح بـ 18 ساعة
            if hasattr(student, 'Semester') and student.Semester == 1:
                return 2.0
            return None
    
    @staticmethod
    def _check_enrollment_period():
        """التحقق من فترة التسجيل النشطة"""
        try:
            current_date = datetime.now()
            current_period = EnrollmentPeriods.query.filter(
                EnrollmentPeriods.StartDate <= current_date,
                EnrollmentPeriods.EndDate >= current_date
            ).first()
            
            if current_period:
                return {
                    "is_active": True,
                    "message": "فترة التسجيل نشطة",
                    "period": current_period
                }
            else:
                # التحقق من وجود فترة قادمة
                future_period = EnrollmentPeriods.query.filter(
                    EnrollmentPeriods.StartDate > current_date
                ).order_by(EnrollmentPeriods.StartDate).first()
                
                if future_period:
                    return {
                        "is_active": False,
                        "message": f"فترة التسجيل ستبدأ في {future_period.StartDate.strftime('%Y-%m-%d')}"
                    }
                else:
                    return {
                        "is_active": False,
                        "message": "لا توجد فترة تسجيل نشطة حالياً"
                    }
                    
        except Exception as e:
            logger.error(f"Error in _check_enrollment_period: {str(e)}")
            return {
                "is_active": False,
                "message": f"حدث خطأ أثناء التحقق من فترة التسجيل: {str(e)}"
            }
    
    @staticmethod
    def _get_current_semester():
        """الحصول على الفصل الدراسي الحالي"""
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year
        
        # تحديد الفصل الدراسي بناءً على الشهر
        if 2 <= current_month < 6:
            # الفصل الربيعي
            return f"ربيع {current_year}"
        elif 9 <= current_month <= 12:
            # الفصل الخريفي
            return f"خريف {current_year}"
        elif current_month == 1:
            # الفصل الخريفي من العام السابق
            return f"شتاء {current_year - 1}"
        else:
            # الفصل الصيفي
            return f"صيف {current_year}"
    
    @staticmethod
    def _check_credit_limit(student, course, current_semester):
        """التحقق من الحد الأقصى للساعات المسموحة للطالب"""
        try:
            # تحديد الحد الأقصى للساعات بناءً على متوسط GPA
            average_gpa = CourseEnrollmentService._calculate_average_gpa(student)
            max_credits = 18 if average_gpa and average_gpa >= 2.0 else 10
            
            # حساب الساعات المسجلة حالياً في الفصل
            current_enrollments = Enrollments.query.filter_by(
                StudentId=student.Id,
                Semester=current_semester,
                IsCompleted="قيد الدراسة"
            ).all()
            
            current_credits = 0
            for enrollment in current_enrollments:
                enrolled_course = Courses.query.get(enrollment.CourseId)
                if enrolled_course:
                    current_credits += enrolled_course.Credits or 0
            
            # التحقق من إمكانية إضافة المادة الجديدة
            new_course_credits = course.Credits or 0
            total_credits_after = current_credits + new_course_credits
            
            if total_credits_after > max_credits:
                # تحديد سبب الحد الأقصى للساعات
                if hasattr(student, 'Semester') and student.Semester == 1:
                    gpa_reason = "(طالب في الترم الأول)"
                elif average_gpa and average_gpa >= 2.0:
                    gpa_reason = f"(متوسط GPA: {average_gpa:.2f})"
                elif average_gpa:
                    gpa_reason = f"(متوسط GPA: {average_gpa:.2f} أقل من 2.0)"
                else:
                    gpa_reason = "(لا توجد درجات GPA)"
                
                return {
                    "allowed": False,
                    "message": f"تجاوز الحد الأقصى للساعات المسموحة. الحد الأقصى: {max_credits} ساعة، المسجل حالياً: {current_credits} ساعة، المطلوب إضافته: {new_course_credits} ساعة {gpa_reason}"
                }
            
            return {
                "allowed": True,
                "message": f"يمكن تسجيل المادة. الساعات المتبقية: {max_credits - total_credits_after}"
            }
            
        except Exception as e:
            logger.error(f"Error in _check_credit_limit: {str(e)}")
            return {
                "allowed": False,
                "message": f"حدث خطأ أثناء التحقق من الساعات: {str(e)}"
            }
    
    @staticmethod
    def _check_course_availability(student_id, course_id):
        """التحقق من أن المادة متاحة للطالب"""
        try:
            # 1. التحقق الأساسي: هل المادة موجودة؟
            course = Courses.query.get(course_id)
            if not course:
                return {
                    "available": False,
                    "message": "المادة غير موجودة"
                }
            
            # 2. التحقق من حالة المادة
            if hasattr(course, 'Status') and course.Status != 'متاح':
                return {
                    "available": False,
                    "message": "المادة غير متاحة حالياً"
                }
            
            # 3. الحصول على بيانات الطالب
            student = Students.query.get(student_id)
            if not student:
                return {
                    "available": False,
                    "message": "الطالب غير موجود"
                }
            
            # 4. التحقق من أن المادة متاحة لشعبة الطالب
            division_check = CourseEnrollmentService._check_course_division_availability(student.DivisionId, course_id)
            if not division_check["available"]:
                return {
                    "available": False,
                    "message": division_check["message"]
                }
            
            # 5. التحقق من المتطلبات السابقة (Prerequisites)
            prerequisite_check = CourseEnrollmentService._check_prerequisites(student_id, course_id)
            if not prerequisite_check["satisfied"]:
                return {
                    "available": False,
                    "message": prerequisite_check["message"]
                }
            
            # 6. التحقق من السعة المتاحة للمادة
            if hasattr(course, 'MaxSeats') and hasattr(course, 'CurrentEnrolledStudents'):
                if course.MaxSeats and course.CurrentEnrolledStudents >= course.MaxSeats:
                    return {
                        "available": False,
                        "message": "المادة مكتملة العدد"
                    }
            
            return {
                "available": True,
                "message": "المادة متاحة للتسجيل"
            }
            
        except Exception as e:
            logger.error(f"Error in _check_course_availability: {str(e)}")
            return {
                "available": False,
                "message": f"حدث خطأ أثناء التحقق من توفر المادة: {str(e)}"
            }
    
    @staticmethod
    def _check_course_division_availability(division_id, course_id):
        """التحقق من أن المادة متاحة لشعبة الطالب من جدول CourseDivisions"""
        try:
            # البحث عن المادة في جدول CourseDivisions للشعبة المحددة
            course_division = CourseDivisions.query.filter_by(
                CourseId=course_id,
                DivisionId=division_id
            ).first()
            
            if not course_division:
                return {
                    "available": False,
                    "message": "المادة غير متاحة لشعبة الطالب"
                }
            
            # المادة متاحة للشعبة سواء كانت إجبارية أو اختيارية
            return {
                "available": True,
                "message": "المادة متاحة لشعبة الطالب"
            }
            
        except Exception as e:
            logger.error(f"Error in _check_course_division_availability: {str(e)}")
            return {
                "available": False,
                "message": f"حدث خطأ أثناء التحقق من توفر المادة للشعبة: {str(e)}"
            }
    
    @staticmethod
    def _check_prerequisites(student_id, course_id):
        """التحقق من المتطلبات السابقة للمادة من جدول CoursePrerequisites"""
        try:
            # الحصول على جميع المتطلبات السابقة للمادة
            prerequisites = CoursePrerequisites.query.filter_by(CourseId=course_id).all()
            
            if not prerequisites:
                # لا توجد متطلبات سابقة
                return {
                    "satisfied": True,
                    "message": "لا توجد متطلبات سابقة للمادة"
                }
            
            # الحصول على المواد المكتملة للطالب
            completed_enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted="مكتملة"
            ).all()
            
            completed_course_ids = [enrollment.CourseId for enrollment in completed_enrollments]
            
            # التحقق من كل متطلب سابق
            missing_prerequisites = []
            
            for prerequisite in prerequisites:
                if prerequisite.PrerequisiteCourseId not in completed_course_ids:
                    # الحصول على اسم المادة المطلوبة
                    required_course = Courses.query.get(prerequisite.PrerequisiteCourseId)
                    course_name = required_course.Name if required_course else f"المادة رقم {prerequisite.PrerequisiteCourseId}"
                    missing_prerequisites.append(course_name)
            
            if missing_prerequisites:
                return {
                    "satisfied": False,
                    "message": f"يجب إكمال المواد التالية أولاً: {', '.join(missing_prerequisites)}"
                }
            
            return {
                "satisfied": True,
                "message": "جميع المتطلبات السابقة مكتملة"
            }
            
        except Exception as e:
            logger.error(f"Error in _check_prerequisites: {str(e)}")
            return {
                "satisfied": False,
                "message": f"حدث خطأ أثناء التحقق من المتطلبات السابقة: {str(e)}"
            }
    
    @staticmethod
    def _get_current_semester_number():
        """الحصول على رقم الفصل الدراسي الحالي"""
        current_date = datetime.now()
        current_month = current_date.month
        
        # تحديد رقم الفصل الدراسي بناءً على الشهر
        if 2 <= current_month <= 6:
            # الفصل الربيعي
            return 2
        elif 9 <= current_month <= 12 or current_month == 1:
            # الفصل الخريفي
            return 1
        else:
            # الفصل الصيفي
            return 3
    

class AcademicWarningService:
    
    WARNING_TYPES = {
        'انخفاض المعدل التراكمي': 'انخفاض المعدل التراكمي',
        'رسوب في المواد': 'رسوب في المواد',
        'نقص الساعات المعتمدة': 'نقص في الساعات المعتمدة',
        'نقص_شديد الساعات المعتمدة': 'نقص شديد في الساعات المعتمدة',
        'إنذار أكاديمي': 'إنذار أكاديمي',
        'خطر فصل أكاديمي': 'خطر فصل أكاديمي'
    }
    
    WARNING_LEVELS = {
        1: 'تنبيه',
        2: 'إنذار أول', 
        3: 'إنذار ثاني',
        4: 'إنذار نهائي'
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _calculate_total_grade(self, enrollment):
        """حساب الدرجة الإجمالية من 150 (30 + 30 + 90)"""
        try:
            exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
            exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
            final_grade = float(enrollment.Grade) if enrollment.Grade else 0
            total_grade = exam1_grade + exam2_grade + final_grade
            
            return {
                'total_grade': total_grade,
                'is_passing': total_grade >= 75  # حد النجاح 75 من 150 (50%)
            }
        except Exception as e:
            self.logger.error(f"خطأ في حساب الدرجة الإجمالية: {str(e)}")
            return {
                'total_grade': 0,
                'is_passing': False
            }

    def check_all_students_warnings(self, semester):
        """فحص جميع الطلاب وإصدار الإنذارات المطلوبة وحل الإنذارات المحسنة"""
        try:
            students = Students.query.filter_by(status='نشط').all()
            warnings_issued = 0
            warnings_resolved = 0
            
            for student in students:
                # فحص وحل الإنذارات المحسنة أولاً
                resolved_count = self.check_and_resolve_warnings(student.Id)
                warnings_resolved += resolved_count
                
                # ثم فحص الإنذارات الجديدة
                warnings = self._evaluate_student_warnings(student, semester)
                for warning in warnings:
                    if self._should_issue_warning(student, warning):
                        self._create_warning(student, warning, semester)
                        warnings_issued += 1
            
            self.logger.info(f"تم إصدار {warnings_issued} إنذار أكاديمي وحل {warnings_resolved} إنذار")
            return {
                'warnings_issued': warnings_issued,
                'warnings_resolved': warnings_resolved,
                'total_processed': warnings_issued + warnings_resolved
            }
            
        except Exception as e:
            self.logger.error(f"خطأ في فحص الإنذارات: {str(e)}")
            return {
                'warnings_issued': 0,
                'warnings_resolved': 0,
                'total_processed': 0,
                'error': str(e)
            }

    def _evaluate_student_warnings(self, student, semester):
        """تقييم الطالب وتحديد الإنذارات المطلوبة"""
        warnings = []
        
        # 1. فحص المعدل التراكمي
        gpa_warning = self._check_gpa_warning(student)
        if gpa_warning:
            warnings.append(gpa_warning)
        
        # 2. فحص الرسوب في المواد
        failing_warning = self._check_failing_courses(student, semester)
        if failing_warning:
            warnings.append(failing_warning)
        
        # 3. فحص قاعدة الفصل (3 ترمات متصلة أو 4 منفصلة)
        dismissal_warning = self._check_dismissal_rule(student)
        if dismissal_warning:
            warnings.append(dismissal_warning)
        
        # 4. فحص الساعات المعتمدة حسب المستوى الدراسي
        credit_warning = self._check_credit_progress(student)
        if credit_warning:
            warnings.append(credit_warning)
        
        return warnings

    def _check_gpa_warning(self, student):
        """فحص المعدل التراكمي مع مراعاة الترم"""
        current_gpa = self._get_current_gpa(student)
        current_semester = student.Semester
        
        if current_gpa is None:
            return None
        
        # الترم الأول: لا توجد إنذارات (الطالب لم يكمل أي ترم بعد)
        if current_semester == 1:
            return None
            
        # الترم الثاني: تخفيف القيود (إنذار فقط إذا كان المعدل أقل من 1.5)
        elif current_semester == 2:
            if current_gpa < 1.5:
                return {
                    'type': 'انخفاض المعدل التراكمي',
                    'level': 2,
                    'description': f'المعدل التراكمي منخفض في بداية الدراسة: {current_gpa:.2f}',
                    'action_required': 'مراجعة مع المرشد الأكاديمي لتحسين الأداء'
                }
        
        # من الترم الثالث فما فوق: تطبيق القواعد العادية
        else:
            if current_gpa < 1.5:
                return {
                    'type': 'انخفاض المعدل التراكمي',
                    'level': 4,
                    'description': f'المعدل التراكمي منخفض جداً: {current_gpa:.2f}',
                    'action_required': 'مراجعة فورية مع المرشد الأكاديمي'
                }
            elif current_gpa < 2.0:
                return {
                    'type': 'انخفاض المعدل التراكمي', 
                    'level': 3,
                    'description': f'المعدل التراكمي منخفض: {current_gpa:.2f}',
                    'action_required': 'تحسين الأداء الأكاديمي'
                }
            elif current_gpa < 2.5:
                return {
                    'type': 'انخفاض المعدل التراكمي',
                    'level': 2, 
                    'description': f'المعدل التراكمي أقل من المطلوب: {current_gpa:.2f}',
                    'action_required': 'مراجعة خطة الدراسة'
                }
        
        return None

    def _check_failing_courses(self, student, semester):
        """فحص الرسوب في المواد - جميع المواد الراسب فيها الطالب في كل الترمات"""
        current_semester = student.Semester
        
        # الترم الأول: لا توجد إنذارات (الطالب لم يكمل أي مواد بعد)
        if current_semester == 1:
            return None
        
        # حساب جميع المواد الراسب فيها الطالب في كل الترمات (اعتماداً على IsCompleted فقط)
        failed_enrollments = Enrollments.query.filter(
            and_(
                Enrollments.StudentId == student.Id,
                Enrollments.IsCompleted == 'راسب'
            )
        ).all()
        
        # حساب المواد الراسب فيها والتي لم يعيدها بنجاح
        failed_courses = {}
        for enrollment in failed_enrollments:
            course_id = enrollment.CourseId
            
            # فحص إذا كان الطالب نجح في هذه المادة في ترم لاحق (اعتماداً على IsCompleted فقط)
            passed_later = Enrollments.query.filter(
                and_(
                    Enrollments.StudentId == student.Id,
                    Enrollments.CourseId == course_id,
                    Enrollments.NumberOFSemster > enrollment.NumberOFSemster,
                    Enrollments.IsCompleted == 'ناجح'
                )
            ).first()
            
            # إذا لم ينجح في المادة لاحقاً، تُحسب كمادة راسب فيها
            if not passed_later:
                # حساب الدرجة الإجمالية للعرض فقط (ليس للحسابات)
                exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                total_grade = exam1_grade + exam2_grade + final_grade
                
                if course_id not in failed_courses:
                    failed_courses[course_id] = {
                        'course_name': enrollment.course.Name if enrollment.course else f'مادة {course_id}',
                        'semester': enrollment.Semester,
                        'total_grade': total_grade  # الدرجة الإجمالية من 150 (للعرض فقط)
                    }
        
        failed_count = len(failed_courses)
        
        if failed_count == 0:
            return None
        
        # تحديد مستوى الإنذار حسب عدد المواد الراسب فيها
        # الترم الثاني: تخفيف القيود
        if current_semester == 2:
            if failed_count >= 2:
                return {
                    'type': 'رسوب في المواد',
                    'level': 2,
                    'description': f'رسوب في {failed_count} مواد في بداية الدراسة',
                    'action_required': 'مراجعة مع المرشد الأكاديمي لتحسين الأداء',
                    'failed_courses': list(failed_courses.values())
                }
        
        # من الترم الثالث فما فوق: تطبيق القواعد العادية
        else:
            if failed_count >= 5:
                return {
                    'type': 'رسوب في المواد',
                    'level': 4,
                    'description': f'رسوب في {failed_count} مواد - خطر أكاديمي',
                    'action_required': 'مراجعة عاجلة مع عميد الكلية',
                    'failed_courses': list(failed_courses.values())
                }
            elif failed_count >= 3:
                return {
                    'type': 'رسوب في المواد',
                    'level': 3,
                    'description': f'رسوب في {failed_count} مواد',
                    'action_required': 'مراجعة عاجلة مع المرشد الأكاديمي',
                    'failed_courses': list(failed_courses.values())
                }
            elif failed_count >= 2:
                return {
                    'type': 'رسوب في المواد',
                    'level': 2,
                    'description': f'رسوب في {failed_count} مواد',
                    'action_required': 'تحسين الأداء في المواد',
                    'failed_courses': list(failed_courses.values())
                }
            elif failed_count >= 1:
                return {
                    'type': 'رسوب في المواد',
                    'level': 1,
                    'description': f'رسوب في مادة واحدة',
                    'action_required': 'متابعة الأداء',
                    'failed_courses': list(failed_courses.values())
                }
        
        return None

    def _check_dismissal_rule(self, student):
        """فحص قاعدة الفصل: 3 ترمات متصلة أو 4 منفصلة بمعدل أقل من 2.0 (من الترم الثالث فما فوق)"""
        try:
            current_semester = student.Semester
            
            # قاعدة الفصل تطبق فقط من الترم الثالث فما فوق
            if current_semester < 3:
                return None
            
            gpa_history = self._get_gpa_history(student)
            
            if len(gpa_history) < 3:
                return None
            
            # فحص المعدلات الأقل من 2.0
            low_gpa_semesters = [g for g in gpa_history if g['cumulative_gpa'] < 2.0]
            
            if len(low_gpa_semesters) >= 4:
                # 4 ترمات منفصلة
                return {
                    'type': 'خطر فصل أكاديمي',
                    'level': 4,
                    'description': f'خطر فصل أكاديمي: 4 ترمات بمعدل أقل من 2.0',
                    'action_required': 'مراجعة عاجلة مع عميد الكلية - خطر الفصل'
                }
            elif len(low_gpa_semesters) >= 3:
                # فحص إذا كانت 3 ترمات متصلة
                recent_semesters = gpa_history[-3:]
                if all(g['cumulative_gpa'] < 2.0 for g in recent_semesters):
                    return {
                        'type': 'خطر فصل أكاديمي',
                        'level': 4,
                        'description': f'خطر فصل أكاديمي: 3 ترمات متصلة بمعدل أقل من 2.0',
                        'action_required': 'مراجعة عاجلة مع عميد الكلية - خطر الفصل'
                    }
                else:
                    return {
                        'type': 'إنذار أكاديمي',
                        'level': 3,
                        'description': f'إنذار أكاديمي: {len(low_gpa_semesters)} ترمات بمعدل أقل من 2.0',
                        'action_required': 'تحسين الأداء فوراً لتجنب الفصل'
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"خطأ في فحص قاعدة الفصل: {str(e)}")
            return None

    def _check_credit_progress(self, student):
        """فحص تقدم الطالب في الساعات المعتمدة حسب المستوى الدراسي"""
        try:
            current_semester = student.Semester
            completed_credits = student.CreditsCompleted
            student_level = getattr(student, 'StudentLevel', None)
            
            # الترم الأول: الطالب لم يكمل أي ساعات بعد
            if current_semester == 1:
                return None
            
            # تحديد المستوى المتوقع حسب الساعات
            def get_expected_level_by_credits(credits):
                if credits <= 33:
                    return 1  # السنة الأولى
                elif credits <= 67:
                    return 2  # السنة الثانية
                elif credits <= 101:
                    return 3  # السنة الثالثة
                else:
                    return 4  # السنة الرابعة
            
            # تحديد الحد الأدنى للساعات حسب الترم
            def get_min_credits_for_semester(semester):
                if semester <= 2:  # السنة الأولى (ترم 1-2)
                    return max(0, (semester - 1) * 15)  # 0, 15
                elif semester <= 4:  # السنة الثانية (ترم 3-4)
                    return 34 + max(0, (semester - 3) * 15)  # 34, 49
                elif semester <= 6:  # السنة الثالثة (ترم 5-6)
                    return 68 + max(0, (semester - 5) * 15)  # 68, 83
                else:  # السنة الرابعة (ترم 7-8)
                    return 102 + max(0, (semester - 7) * 15)  # 102, 117
            
            expected_min_credits = get_min_credits_for_semester(current_semester)
            expected_level = get_expected_level_by_credits(completed_credits)
            
            # حساب النقص في الساعات
            credit_deficit = expected_min_credits - completed_credits
            
            # فحص إذا كان المستوى الفعلي أقل من المتوقع
            semester_to_level = {
                1: 1, 2: 1,  # السنة الأولى
                3: 2, 4: 2,  # السنة الثانية
                5: 3, 6: 3,  # السنة الثالثة
                7: 4, 8: 4   # السنة الرابعة
            }
            
            expected_level_by_semester = semester_to_level.get(current_semester, 4)
            
            # إنذارات حسب شدة النقص
            if credit_deficit > 30 or expected_level < expected_level_by_semester:
                return {
                    'type': 'نقص شديد الساعات المعتمدة',
                    'level': 3,
                    'description': f'نقص شديد في الساعات: {credit_deficit} ساعة (مكتمل: {completed_credits}, متوقع: {expected_min_credits}) - المستوى الحالي: {expected_level}, المتوقع: {expected_level_by_semester}',
                    'action_required': 'إعادة تخطيط البرنامج الدراسي والتسجيل في ساعات إضافية'
                }
            elif credit_deficit > 15:
                return {
                    'type': 'نقص الساعات المعتمدة',
                    'level': 2,
                    'description': f'نقص في الساعات المعتمدة: {credit_deficit} ساعة (مكتمل: {completed_credits}, متوقع: {expected_min_credits})',
                    'action_required': 'تسجيل ساعات إضافية في الترم القادم'
                }
            elif credit_deficit > 5:
                return {
                    'type': 'نقص الساعات المعتمدة',
                    'level': 1,
                    'description': f'تأخر طفيف في الساعات: {credit_deficit} ساعة (مكتمل: {completed_credits}, متوقع: {expected_min_credits})',
                    'action_required': 'متابعة التقدم الأكاديمي'
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"خطأ في فحص تقدم الساعات: {str(e)}")
            return None

    def _get_current_gpa(self, student):
        """حساب المعدل التراكمي الحالي (تراكمي وليس متوسط)"""
        current_semester = student.Semester
        
        if current_semester <= 1:
            # الترم الأول: لا يوجد معدل تراكمي بعد
            return None
        
        # الحصول على المعدل التراكمي للترم الحالي
        gpa_field = f'GPA{current_semester - 1}'  # المعدل للترم المكتمل
        if hasattr(student, gpa_field):
            gpa_value = getattr(student, gpa_field, None)
            if gpa_value is not None:
                return float(gpa_value)
        
        return None

    def _get_gpa_history(self, student):
        """الحصول على تاريخ المعدلات التراكمية"""
        current_semester = student.Semester
        gpa_history = []
        
        # جلب المعدلات من الترم 1 حتى الترم المكتمل
        for i in range(1, current_semester):
            gpa_field = f'GPA{i}'
            if hasattr(student, gpa_field):
                gpa_value = getattr(student, gpa_field, None)
                if gpa_value is not None:
                    gpa_history.append({
                        'semester': i,
                        'cumulative_gpa': float(gpa_value)
                    })
        
        return gpa_history

    def _should_issue_warning(self, student, warning):
        """تحديد ما إذا كان يجب إصدار الإنذار أم لا (منع التكرار)"""
        try:
            # فحص إذا كان يوجد إنذار مشابه نشط
            existing_warning = AcademicWarnings.query.filter(
                and_(
                    AcademicWarnings.StudentId == student.Id,
                    AcademicWarnings.WarningType == warning['type'],
                    AcademicWarnings.Status == 'Active'
                )
            ).first()
            
            if existing_warning:
                # إذا كان الإنذار الجديد أعلى مستوى، يتم إصداره
                if warning['level'] > existing_warning.WarningLevel:
                    return True
                # إذا كان نفس المستوى أو أقل، لا يتم إصداره
                else:
                    self.logger.info(f"إنذار مشابه موجود بالفعل للطالب {student.Name}: {warning['type']} - المستوى {existing_warning.WarningLevel}")
                    return False
            
            # إذا لم يوجد إنذار مشابه، يتم إصداره
            return True
            
        except Exception as e:
            self.logger.error(f"خطأ في فحص تكرار الإنذارات: {str(e)}")
            return True  # في حالة الخطأ، يتم إصدار الإنذار احتياطياً

    def _create_warning(self, student, warning, semester):
        """إنشاء إنذار أكاديمي جديد"""
        try:
            # Close any existing active warnings of the same type
            existing_warnings = AcademicWarnings.query.filter(
                and_(
                    AcademicWarnings.StudentId == student.Id,
                    AcademicWarnings.WarningType == warning['type'],
                    AcademicWarnings.Status == 'نشط'
                )
            ).all()
            
            for existing in existing_warnings:
                existing.Status = 'Superseded'
                existing.ResolvedDate = datetime.now()
            
            # إعداد الملاحظات مع تفاصيل المواد الراسب فيها إن وجدت
            notes = f"تم إصدار الإنذار تلقائياً بواسطة النظام"
            if 'failed_courses' in warning and warning['failed_courses']:
                failed_courses_info = []
                for course in warning['failed_courses']:
                    course_info = f"- {course['course_name']} (الترم: {course['semester']}"
                    if course.get('total_grade') is not None:
                        course_info += f", الدرجة الإجمالية: {course['total_grade']}/150"
                    course_info += ")"
                    failed_courses_info.append(course_info)
                
                notes += f"\n\nالمواد الراسب فيها:\n" + "\n".join(failed_courses_info)
            
            # Create new warning
            new_warning = AcademicWarnings(
                StudentId=student.Id,
                WarningType=warning['type'],
                WarningLevel=warning['level'],
                Description=warning['description'],
                Semester=semester,
                IssueDate=datetime.now(),
                Status='نشط',
                ActionRequired=warning['action_required'],
                Notes=notes
            )
            
            db.session.add(new_warning)
            db.session.commit()
            
            self.logger.info(f"تم إصدار إنذار للطالب {student.Name}: {warning['description']}")
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"خطأ في إنشاء الإنذار: {str(e)}")

    def resolve_warning(self, warning_id, notes=""):
        """حل الإنذار الأكاديمي"""
        try:
            warning = AcademicWarnings.query.get(warning_id)
            if warning:
                warning.Status = 'Resolved'
                warning.ResolvedDate = datetime.now()
                warning.Notes += f" | تم الحل: {notes}"
                db.session.commit()
                return True
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"خطأ في حل الإنذار: {str(e)}")
        return False

    def get_student_warnings(self, student_id, status=None):
        """الحصول على إنذارات طالب معين"""
        try:
            query = AcademicWarnings.query.filter_by(StudentId=student_id)
            if status:
                query = query.filter_by(Status=status)
            
            warnings = query.order_by(AcademicWarnings.IssueDate.desc()).all()
            return warnings
        except Exception as e:
            self.logger.error(f"خطأ في جلب الإنذارات: {str(e)}")
            return []

    def get_all_active_warnings(self):
        """الحصول على جميع الإنذارات النشطة"""
        try:
            warnings = AcademicWarnings.query.filter_by(Status='نشط').order_by(
                AcademicWarnings.WarningLevel.desc(),
                AcademicWarnings.IssueDate.desc()
            ).all()
            return warnings
        except Exception as e:
            self.logger.error(f"خطأ في جلب الإنذارات النشطة: {str(e)}")
            return []

    def get_current_semester(self):
        """الحصول على الفصل الدراسي الحالي"""
        from datetime import datetime
        now = datetime.now()
        if now.month >= 9 or now.month <= 1:
            return f"خريف {now.year}"
        elif now.month >= 2 and now.month < 6:
            return f"ربيع {now.year}"
        else:
            return f"صيف {now.year}"

    def check_and_resolve_warnings(self, student_id):
        """فحص وحل الإنذارات تلقائياً عند تحسن الأداء"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return False
            
            # الحصول على الإنذارات النشطة للطالب
            active_warnings = AcademicWarnings.query.filter(
                and_(
                    AcademicWarnings.StudentId == student_id,
                    AcademicWarnings.Status == 'نشط'
                )
            ).all()
            
            resolved_count = 0
            
            for warning in active_warnings:
                should_resolve = False
                resolution_reason = ""
                
                # فحص إنذارات الرسوب
                if warning.WarningType == 'رسوب في المواد':
                    # إعادة حساب المواد الراسب فيها حالياً
                    current_warnings = self._evaluate_student_warnings(student, self.get_current_semester())
                    failing_warning = None
                    
                    for w in current_warnings:
                        if w['type'] == 'رسوب في المواد':
                            failing_warning = w
                            break
                    
                    # إذا لم يعد هناك إنذار رسوب أو انخفض مستواه بشكل كبير
                    if not failing_warning:
                        should_resolve = True
                        resolution_reason = "تم النجاح في جميع المواد المطلوبة"
                    elif failing_warning['level'] < warning.WarningLevel - 1:
                        should_resolve = True
                        resolution_reason = f"تحسن الأداء - انخفض عدد المواد الراسب فيها"
                
                # فحص إنذارات المعدل التراكمي
                elif warning.WarningType == 'انخفاض المعدل التراكمي':
                    current_gpa = self._get_current_gpa(student)
                    if current_gpa and current_gpa >= 2.5:
                        should_resolve = True
                        resolution_reason = f"تحسن المعدل التراكمي إلى {current_gpa:.2f}"
                    elif current_gpa and current_gpa >= 2.0 and warning.WarningLevel >= 3:
                        should_resolve = True
                        resolution_reason = f"تحسن المعدل التراكمي إلى {current_gpa:.2f}"
                
                # فحص إنذارات الساعات المعتمدة
                elif 'الساعات المعتمدة' in warning.WarningType:
                    credit_warning = self._check_credit_progress(student)
                    if not credit_warning:
                        should_resolve = True
                        resolution_reason = "تم استكمال الساعات المطلوبة"
                    elif credit_warning['level'] < warning.WarningLevel:
                        should_resolve = True
                        resolution_reason = "تحسن في عدد الساعات المكتملة"
                
                # حل الإنذار إذا كان مطلوباً
                if should_resolve:
                    warning.Status = 'محلول'
                    warning.ResolvedDate = datetime.now()
                    warning.Notes += f" | تم الحل تلقائياً: {resolution_reason}"
                    resolved_count += 1
            
            if resolved_count > 0:
                db.session.commit()
                self.logger.info(f"تم حل {resolved_count} إنذار تلقائياً للطالب {student.Name}")
            
            return resolved_count
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"خطأ في فحص وحل الإنذارات: {str(e)}")
            return 0

class AcademicStatusAnalysisService:
    """خدمة تحليل الوضع الأكاديمي للطلاب"""
    
    @staticmethod
    def get_comprehensive_analysis(student_id: int) -> Dict:
        """تحليل شامل للوضع الأكاديمي للطالب"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            # جمع جميع التحليلات
            basic_info = AcademicStatusAnalysisService._get_student_basic_info(student)
            gpa_trends = AcademicStatusAnalysisService._analyze_gpa_trends(student_id)
            performance_patterns = AcademicStatusAnalysisService._analyze_performance_patterns(student_id)
            risk_assessment = AcademicStatusAnalysisService._calculate_risk_assessment(student_id)
            course_analysis = AcademicStatusAnalysisService._analyze_course_performance(student_id)
            attendance_insights = AcademicStatusAnalysisService._analyze_attendance_patterns(student_id)
            warnings_summary = AcademicStatusAnalysisService._get_warnings_summary(student_id)
            peer_comparison = AcademicStatusAnalysisService._compare_with_peers(student_id)
            predictions = AcademicStatusAnalysisService._get_merged_predictions(student_id)
            interventions = AcademicStatusAnalysisService._predictive_intervention_system(student_id)
            ai_insights = AcademicStatusAnalysisService._generate_ai_insights(student_id)
            
            # إزالة التكرارات
            # إزالة current_gpa من التحليلات الأخرى لأنه موجود في basic_info
            if 'current_gpa' in gpa_trends:
                del gpa_trends['current_gpa']
            if 'current_gpa' in risk_assessment:
                del risk_assessment['current_gpa']
            if 'current_gpa' in predictions:
                del predictions['current_gpa']
            
            # إزالة gpa_history من predictions لأنه موجود في gpa_analysis
            if 'gpa_history' in predictions:
                del predictions['gpa_history']
            
            return {
                "student_info": basic_info,
                "gpa_analysis": gpa_trends,
                "performance_patterns": performance_patterns,
                "risk_assessment": risk_assessment,
                "course_analysis": course_analysis,
                "attendance_insights": attendance_insights,
                "academic_warnings_summary": warnings_summary,
                "peer_comparison": peer_comparison,
                "predictions": predictions,
                "predictive_interventions": interventions,
                "ai_insights": ai_insights
            }
            
        except Exception as e:
            return {"error": f"Comprehensive analysis failed: {str(e)}"}
    
    @staticmethod
    def _get_student_basic_info(student: Students) -> Dict:
        return {
            "student_id": student.Id,
            "name": student.Name,
            "division": student.division.Name if student.division else "غير محدد",
            "level": student.StudentLevel,
            "semester": student.Semester,
            "enrollment_date": student.EnrollmentDate.isoformat() if student.EnrollmentDate else None,
            "current_gpa": AcademicStatusAnalysisService._get_current_gpa(student)
        }
    
    @staticmethod
    def _analyze_gpa_trends(student_id: int) -> Dict:
        """تحليل اتجاهات المعدل التراكمي"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            # الطالب في الترم X يعني أنه أكمل الترم X-1
            completed_semester = student.Semester - 1
            
            if completed_semester <= 0:
                return {
                    "trend": "no_data",
                    "slope": 0,
                    "current_gpa": 0,
                    "interpretation": "الطالب لم يكمل أي فصل دراسي بعد"
                }
            
            # جمع معدلات الفصول المكتملة وحساب المعدل التراكمي
            gpa_history = []
            cumulative_gpas = []
            semesters = []
            
            total_gpa = 0.0
            
            for i in range(1, completed_semester + 1):
                semester_gpa = getattr(student, f'GPA{i}', None)
                if semester_gpa is not None:
                    gpa_history.append(float(semester_gpa))
                    total_gpa += float(semester_gpa)
                    # المعدل التراكمي حتى هذا الفصل
                    cumulative_gpa = total_gpa / i
                    cumulative_gpas.append(cumulative_gpa)
                    semesters.append(i)
            
            if len(cumulative_gpas) < 2:
                return {
                    "trend": "insufficient_data",
                    
                    "current_gpa": cumulative_gpas[0] if cumulative_gpas else 0,
                    "interpretation": "بيانات غير كافية لتحديد الاتجاه"
                }
            
            # حساب الاتجاه باستخدام الانحدار الخطي
            X = np.array(semesters).reshape(-1, 1)
            y = np.array(cumulative_gpas)
            
            model = LinearRegression()
            model.fit(X, y)
            slope = model.coef_[0]
            
            # تحديد الاتجاه
            if slope > 0.1:
                trend = "متحسن"
            elif slope < -0.1:
                trend = "متراجع"
            else:
                trend = "مستقر"
            
            return {
                "trend": trend,
                
                "current_gpa": round(cumulative_gpas[-1], 2),
                "cumulative_gpas": [round(gpa, 2) for gpa in cumulative_gpas],
                "semesters": semesters,
                "interpretation": AcademicStatusAnalysisService._interpret_gpa_trend(trend, slope, cumulative_gpas[-1])
            }
            
        except Exception as e:
            return {"error": f"GPA trend analysis failed: {str(e)}"}
    
    @staticmethod
    def _interpret_gpa_trend(trend: str, slope: float, current_gpa: float) -> str:
        """تفسير اتجاه المعدل التراكمي"""
        if trend == "متحسن":
            if current_gpa >= 3.5:
                return f"أداء ممتاز ومتحسن باستمرار (معدل التحسن: {slope:.3f} نقطة/فصل)"
            elif current_gpa >= 3.0:
                return f"أداء جيد ومتحسن (معدل التحسن: {slope:.3f} نقطة/فصل)"
            else:
                return f"تحسن ملحوظ في الأداء (معدل التحسن: {slope:.3f} نقطة/فصل)"
        elif trend == "متراجع":
            if current_gpa >= 3.0:
                return f"انخفاض في الأداء يحتاج متابعة (معدل الانخفاض: {abs(slope):.3f} نقطة/فصل)"
            else:
                return f"تراجع مقلق في الأداء يحتاج تدخل فوري (معدل الانخفاض: {abs(slope):.3f} نقطة/فصل)"
        else:
            if current_gpa >= 3.5:
                return "أداء ممتاز ومستقر"
            elif current_gpa >= 3.0:
                return "أداء جيد ومستقر"
            elif current_gpa >= 2.0:
                return "أداء مقبول ولكن يحتاج تحسين"
            else:
                return "أداء ضعيف يحتاج تدخل عاجل"
    
    @staticmethod
    def _analyze_performance_patterns(student_id: int) -> Dict:
        """تحليل أنماط الأداء الأكاديمي"""
        try:
            enrollments = Enrollments.query.filter_by(StudentId=student_id).all()
            if not enrollments:
                return {"error": "No enrollment data found"}
            
            # تحليل الأداء حسب الفصل الدراسي
            semester_performance = {}
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    # تحويل إلى نسبة مئوية
                    percentage = (total_grade / 150.0) * 100
                    
                    semester = enrollment.Semester
                    if semester not in semester_performance:
                        semester_performance[semester] = []
                    semester_performance[semester].append(percentage)
            
            # حساب متوسط كل فصل مع التقريب
            semester_averages = {}
            for semester, grades in semester_performance.items():
                semester_averages[semester] = round(statistics.mean(grades), 2)
            
            # تحليل الأداء حسب عدد الساعات المعتمدة
            credits_performance = {}
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None and
                    hasattr(enrollment, 'course') and enrollment.course):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    credits = enrollment.course.Credits
                    if credits not in credits_performance:
                        credits_performance[credits] = []
                    credits_performance[credits].append(percentage)
            
            # حساب متوسط الأداء حسب الساعات المعتمدة مع التقريب
            credits_averages = {}
            for credits, grades in credits_performance.items():
                credits_averages[credits] = round(statistics.mean(grades), 2)
            
            # تحديد النمط العام
            pattern = AcademicStatusAnalysisService._identify_performance_patterns(
                semester_averages, credits_averages
            )
            
            # إضافة تحليل أكثر تفصيلاً
            analysis_details = AcademicStatusAnalysisService._generate_performance_insights(
                semester_averages, credits_averages, pattern
            )
            
            return {
                "semester_performance": semester_averages,
                "credits_performance": credits_averages,
                "pattern": pattern,
                "best_semester": max(semester_averages.keys(), key=lambda k: semester_averages[k]) if semester_averages else None,
                "worst_semester": min(semester_averages.keys(), key=lambda k: semester_averages[k]) if semester_averages else None,
                "optimal_credit_load": max(credits_averages.keys(), key=lambda k: credits_averages[k]) if credits_averages else None,
                "performance_insights": analysis_details,
                "improvement_suggestions": AcademicStatusAnalysisService._generate_performance_suggestions(
                    semester_averages, credits_averages, pattern
                )
            }
            
        except Exception as e:
            return {"error": f"Performance pattern analysis failed: {str(e)}"}
    
    @staticmethod
    def _generate_performance_insights(semester_averages: Dict, credits_averages: Dict, pattern: str) -> Dict:
        """توليد رؤى مفصلة حول الأداء"""
        insights = {}
        
        try:
            # تحليل الفصول الدراسية
            if semester_averages:
                semester_values = list(semester_averages.values())
                insights["semester_analysis"] = {
                    "average_performance": round(statistics.mean(semester_values), 2),
                    "performance_range": {
                        "highest": max(semester_values),
                        "lowest": min(semester_values),
                        "difference": round(max(semester_values) - min(semester_values), 2)
                    },
                    "consistency": "مستقر" if statistics.variance(semester_values) < 25 else "متذبذب"
                }
            
            # تحليل الساعات المعتمدة
            if credits_averages:
                insights["credits_analysis"] = {
                    "performance_by_load": credits_averages,
                    "optimal_load_explanation": AcademicStatusAnalysisService._explain_optimal_load(credits_averages),
                    "load_recommendation": AcademicStatusAnalysisService._recommend_credit_load(credits_averages)
                }
            
            # تحليل النمط
            insights["pattern_analysis"] = {
                "current_pattern": pattern,
                "pattern_explanation": AcademicStatusAnalysisService._explain_pattern(pattern),
                "expected_trajectory": AcademicStatusAnalysisService._predict_trajectory(pattern, semester_averages)
            }
            
            return insights
            
        except Exception as e:
            return {"error": f"Performance insights generation failed: {str(e)}"}
    
    @staticmethod
    def _explain_optimal_load(credits_averages: Dict) -> str:
        """شرح العبء الدراسي الأمثل"""
        if not credits_averages:
            return "لا توجد بيانات كافية لتحديد العبء الأمثل"
        
        best_credits = max(credits_averages.keys(), key=lambda k: credits_averages[k])
        best_performance = credits_averages[best_credits]
        
        explanations = {
            2: f"أداؤك أفضل في المواد ذات الساعتين ({best_performance}%) - قد تحتاج تركيز أكبر",
            3: f"أداؤك متوازن في المواد ذات الثلاث ساعات ({best_performance}%) - عبء مناسب",
            4: f"أداؤك ممتاز في المواد الثقيلة ({best_performance}%) - يمكنك تحمل عبء أكبر"
        }
        
        return explanations.get(int(best_credits), f"أداؤك الأفضل في المواد ذات {best_credits} ساعات")
    
    @staticmethod
    def _recommend_credit_load(credits_averages: Dict) -> str:
        """توصية العبء الدراسي"""
        if not credits_averages:
            return "ابدأ بعبء متوسط (15-18 ساعة)"
        
        best_credits = max(credits_averages.keys(), key=lambda k: credits_averages[k])
        best_performance = credits_averages[best_credits]
        
        if best_performance >= 80:
            return f"يمكنك زيادة العبء - ركز على المواد ذات {best_credits} ساعات"
        elif best_performance >= 70:
            return f"حافظ على العبء الحالي مع التركيز على المواد ذات {best_credits} ساعات"
        else:
            return f"قلل العبء وركز على تحسين الأداء في المواد ذات {best_credits} ساعات"
    
    @staticmethod
    def _explain_pattern(pattern: str) -> str:
        """شرح نمط الأداء"""
        explanations = {
            "متحسن مع الوقت": "أداؤك يتحسن باستمرار - استمر على نفس النهج وستصل لنتائج أفضل",
            "متراجع مع الوقت": "هناك تراجع في أداؤك - راجع طريقة دراستك وحدد أسباب التراجع",
            "أداء ثابت": "أداؤك مستقر - حاول تطوير استراتيجيات جديدة للتحسين",
            "أداء متذبذب": "أداؤك غير منتظم - ركز على الاستقرار وتنظيم الوقت",
            "أداء مستقر": "أداؤك منتظم - يمكنك البناء على هذا الاستقرار للتحسين"
        }
        
        return explanations.get(pattern, "نمط أداء عادي - ركز على التحسين المستمر")
    
    @staticmethod
    def _predict_trajectory(pattern: str, semester_averages: Dict) -> str:
        """توقع مسار الأداء"""
        if not semester_averages:
            return "لا توجد بيانات كافية للتوقع"
        
        current_avg = statistics.mean(list(semester_averages.values()))
        
        trajectories = {
            "متحسن مع الوقت": f"متوقع وصولك لمعدل {round(current_avg + 5, 2)}% في الفصول القادمة",
            "متراجع مع الوقت": f"احذر من انخفاض المعدل إلى {round(current_avg - 5, 2)}% إذا لم تتدخل",
            "أداء ثابت": f"متوقع استمرار أداؤك حول {round(current_avg, 2)}%",
            "أداء متذبذب": "أداؤك قد يتراوح بين الارتفاع والانخفاض - ركز على الاستقرار",
            "أداء مستقر": f"متوقع تحسن تدريجي إلى {round(current_avg + 3, 2)}% مع الجهد المناسب"
        }
        
        return trajectories.get(pattern, "مسار الأداء يعتمد على جهدك القادم")
    
    @staticmethod
    def _generate_performance_suggestions(semester_averages: Dict, credits_averages: Dict, pattern: str) -> List[str]:
        """توليد اقتراحات لتحسين الأداء"""
        suggestions = []
        
        try:
            # اقتراحات حسب النمط
            if pattern == "متراجع مع الوقت":
                suggestions.extend([
                    "راجع طريقة دراستك وحدد نقاط الضعف",
                    "اطلب المساعدة من الأساتذة أو الزملاء المتفوقين",
                    "قلل من المشتتات وركز على الدراسة"
                ])
            elif pattern == "أداء متذبذب":
                suggestions.extend([
                    "ضع جدول دراسي ثابت والتزم به",
                    "راجع المواد بانتظام بدلاً من المراجعة المكثفة",
                    "حدد أوقات ثابتة للدراسة يومياً"
                ])
            elif pattern == "متحسن مع الوقت":
                suggestions.extend([
                    "استمر على نفس النهج الناجح",
                    "فكر في تحدي نفسك بمواد أكثر صعوبة",
                    "ساعد زملاءك المحتاجين للمساعدة"
                ])
            
            # اقتراحات حسب الأداء العام
            if semester_averages:
                avg_performance = statistics.mean(list(semester_averages.values()))
                if avg_performance < 60:
                    suggestions.extend([
                        "ركز على فهم الأساسيات قبل الانتقال للمواضيع المتقدمة",
                        "خصص وقت أكبر للمراجعة والممارسة",
                        "فكر في الحصول على دروس خصوصية"
                    ])
                elif avg_performance < 75:
                    suggestions.extend([
                        "حسن من تقنيات الدراسة والمذاكرة",
                        "شارك في مجموعات الدراسة",
                        "راجع الأخطاء في الامتحانات السابقة"
                    ])
                else:
                    suggestions.extend([
                        "حافظ على مستواك الممتاز",
                        "ساعد في تدريس الزملاء لتعزيز فهمك",
                        "فكر في المشاركة في الأنشطة البحثية"
                    ])
            
            return suggestions[:5]  # أقصى 5 اقتراحات
            
        except Exception:
            return ["راجع أداؤك مع المرشد الأكاديمي لوضع خطة تحسين مناسبة"]
    
    @staticmethod
    def _identify_performance_patterns(semester_performance: Dict, credits_performance: Dict) -> str:
        """تحديد نمط الأداء الأكاديمي"""
        if not semester_performance:
            return "بيانات غير كافية"
        
        semester_averages = list(semester_performance.values())
        
        # تحليل الاتجاه العام
        if len(semester_averages) >= 3:
            recent_avg = statistics.mean(semester_averages[-2:])
            early_avg = statistics.mean(semester_averages[:2])
            
            if recent_avg > early_avg + 0.3:
                return "متحسن مع الوقت"
            elif recent_avg < early_avg - 0.3:
                return "متراجع مع الوقت"
        
        # تحليل الاستقرار
        if len(semester_averages) >= 2:
            variance = statistics.variance(semester_averages)
            if variance < 0.1:
                return "أداء ثابت"
            elif variance > 0.5:
                return "أداء متذبذب"
        
        return "أداء مستقر"
    
    @staticmethod
    def _calculate_risk_assessment(student_id: int) -> Dict:
        """حساب تقييم المخاطر الأكاديمية"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
        
            risk_factors = []
            risk_score = 0
        
            # تقييم المعدل التراكمي
            current_gpa = AcademicStatusAnalysisService._get_current_gpa(student)
            if current_gpa < 2.0:
                risk_factors.append("معدل تراكمي منخفض جداً")
                risk_score += 40
            elif current_gpa < 2.5:
                risk_factors.append("معدل تراكمي منخفض")
                risk_score += 25
            elif current_gpa < 3.0:
                risk_factors.append("معدل تراكمي يحتاج تحسين")
                risk_score += 10
            
            # تقييم الإنذارات الأكاديمية
            warnings_count = AcademicWarnings.query.filter_by(StudentId=student_id).count()
            if warnings_count >= 3:
                risk_factors.append("عدد كبير من الإنذارات الأكاديمية")
                risk_score += 30
            elif warnings_count >= 1:
                risk_factors.append("وجود إنذارات أكاديمية")
                risk_score += 15
            
            # تقييم معدل الحضور
            attendance_rate = AcademicStatusAnalysisService._calculate_attendance_rate(student_id)
            if attendance_rate < 0.7:
                risk_factors.append("معدل حضور منخفض")
                risk_score += 20
            elif attendance_rate < 0.8:
                risk_factors.append("معدل حضور يحتاج تحسين")
                risk_score += 10
        
            # تحديد مستوى المخاطرة
            if risk_score >= 60:
                risk_level = "عالي"
            elif risk_score >= 30:
                risk_level = "متوسط"
            else:
                risk_level = "منخفض"
        
            return {
                "risk_level": risk_level,
                "risk_score": risk_score,
                "risk_factors": risk_factors,
                "recommendations": AcademicStatusAnalysisService._get_risk_recommendations(risk_level, risk_factors),
                "current_gpa": current_gpa,
                "attendance_rate": attendance_rate,
                "warnings_count": warnings_count
            }
            
        except Exception as e:
            return {"error": f"Risk assessment failed: {str(e)}"}
    
    @staticmethod
    def _calculate_attendance_rate(student_id: int) -> float:
        """حساب معدل الحضور"""
        try:
            total_sessions = Attendances.query.filter_by(StudentId=student_id).count()
            if total_sessions == 0:
                return 1.0  # افتراض حضور كامل إذا لم توجد بيانات
            
            attended_sessions = Attendances.query.filter_by(
            StudentId=student_id, 
                Status='1'
        ).count()
        
            return round(attended_sessions / total_sessions, 2)
            
        except Exception:
            return 1.0
    
    @staticmethod
    def _get_risk_recommendations(risk_level: str, risk_factors: List[str]) -> List[str]:
        """الحصول على توصيات بناءً على مستوى المخاطرة"""
        recommendations = []
        
        if risk_level == "عالي":
            recommendations.extend([
                "ضرورة مقابلة المرشد الأكاديمي فوراً",
                "وضع خطة دراسية مكثفة للتحسين",
                "تقليل العبء الدراسي إذا أمكن",
                "الحصول على دعم أكاديمي إضافي"
            ])
        elif risk_level == "متوسط":
            recommendations.extend([
                "مراجعة الخطة الدراسية مع المرشد الأكاديمي",
                "تحسين عادات الدراسة",
                "زيادة التركيز على المواد الضعيفة"
            ])
        else:
            recommendations.extend([
                "الحفاظ على الأداء الحالي",
                "التطلع لتحسين المعدل أكثر"
            ])
        
        # توصيات خاصة بعوامل المخاطرة
        for factor in risk_factors:
            if "حضور" in factor:
                recommendations.append("تحسين الانتظام في الحضور")
            if "إنذار" in factor:
                recommendations.append("العمل على تجنب الإنذارات المستقبلية")
            if "معدل" in factor:
                recommendations.append("التركيز على رفع المعدل التراكمي")
        
        return list(set(recommendations))  # إزالة التكرار
    
    @staticmethod
    def _analyze_course_performance(student_id: int) -> Dict:
        """تحليل أداء المواد الدراسية"""
        try:
            enrollments = Enrollments.query.filter_by(StudentId=student_id).all()
            if not enrollments:
                return {"error": "No enrollment data found"}
            
            # جمع بيانات المواد الدراسية
            course_data = {}
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None and 
                    hasattr(enrollment, 'course') and enrollment.course):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    
                    # تحويل إلى نسبة مئوية
                    percentage = (total_grade / 150.0) * 100
                    
                    course = enrollment.course
                    course_key = f"{course.Code} - {course.Name}"
                    
                    if course_key not in course_data:
                        course_data[course_key] = {
                            "course_id": course.Id,
                            "course_name": course.Name,
                            "course_code": course.Code,
                            "grades": [],
                            "total_grades": [],
                            "exam1_grades": [],
                            "exam2_grades": [],
                            "coursework_grades": []
                        }
                    
                    course_data[course_key]["grades"].append(percentage)
                    course_data[course_key]["total_grades"].append(total_grade)
                    course_data[course_key]["exam1_grades"].append(float(enrollment.Exam1Grade))
                    course_data[course_key]["exam2_grades"].append(float(enrollment.Exam2Grade))
                    course_data[course_key]["coursework_grades"].append(float(enrollment.Grade))
            
            # حساب متوسط الأداء لكل مادة ومقارنة مع متوسط الطلاب
            course_performance = {}
            for course_key, data in course_data.items():
                student_avg = round(statistics.mean(data["grades"]), 2)
                
                # تحليل مفصل لكل مادة
                detailed_analysis = {
                    "overall_average": student_avg,
                    "exam1_average": round(statistics.mean(data["exam1_grades"]), 2),
                    "exam2_average": round(statistics.mean(data["exam2_grades"]), 2),
                    "coursework_average": round(statistics.mean(data["coursework_grades"]), 2),
                    "attempts": len(data["grades"]),
                    "grade_trend": AcademicStatusAnalysisService._analyze_grade_trend(data["grades"]),
                    "strengths_weaknesses": AcademicStatusAnalysisService._identify_strengths_weaknesses(
                        data["exam1_grades"], data["exam2_grades"], data["coursework_grades"]
                    )
                }
                
                # حساب متوسط جميع الطلاب في هذه المادة
                course_id = data["course_id"]
                all_enrollments = Enrollments.query.filter_by(CourseId=course_id).all()
                
                peer_grades = []
                for enroll in all_enrollments:
                    if (enroll.StudentId != student_id and 
                        enroll.Grade is not None and 
                        enroll.Exam1Grade is not None and 
                        enroll.Exam2Grade is not None):
                        
                        peer_total = (float(enroll.Exam1Grade) + 
                                    float(enroll.Exam2Grade) + 
                                    float(enroll.Grade))
                        peer_percentage = (peer_total / 150.0) * 100
                        peer_grades.append(peer_percentage)
                
                # تحديد حالة الطالب بالنسبة للمتوسط
                if peer_grades:
                    peer_avg = round(statistics.mean(peer_grades), 2)
                    comparison = AcademicStatusAnalysisService._compare_with_class_average(student_avg, peer_avg)
                else:
                    peer_avg = 0
                    comparison = {
                        "status": "لا توجد بيانات للمقارنة",
                        "difference": 0,
                        "interpretation": "لا يمكن المقارنة مع الزملاء"
                    }
                
                course_performance[course_key] = {
                    "course_name": data["course_name"],
                    "course_code": data["course_code"],
                    "detailed_analysis": detailed_analysis,
                    "peer_comparison": {
                        "peer_average": peer_avg,
                        "comparison": comparison
                    },
                    "improvement_suggestions": AcademicStatusAnalysisService._generate_course_suggestions(
                        detailed_analysis, comparison
                    )
                }
            
            # تحديد أفضل وأسوأ المواد مع التفسير
            performance_summary = AcademicStatusAnalysisService._generate_performance_summary(course_performance)
            
            return {
                "course_performance": course_performance,
                "performance_summary": performance_summary,
                "total_courses": len(course_performance),
                "overall_insights": AcademicStatusAnalysisService._generate_overall_course_insights(course_performance)
            }
            
        except Exception as e:
            return {"error": f"Course performance analysis failed: {str(e)}"}
    
    @staticmethod
    def _analyze_grade_trend(grades: List[float]) -> Dict:
        """تحليل اتجاه الدرجات في المادة"""
        if len(grades) < 2:
            # بدلاً من insufficient_data، نعطي تحليل مفيد للمحاولة الواحدة
            grade = grades[0] if grades else 0
            if grade >= 80:
                return {
                    "trend": "أداء ممتاز",
                    "description": "أداء ممتاز في المحاولة الأولى"
                }
            elif grade >= 70:
                return {
                    "trend": "أداء جيد",
                    "description": "أداء جيد في المحاولة الأولى"
                }
            elif grade >= 60:
                return {
                    "trend": "أداء مقبول",
                    "description": "أداء مقبول في المحاولة الأولى"
                }
            else:
                return {
                    "trend": "يحتاج تحسين",
                    "description": "الأداء يحتاج تحسين في المحاولات القادمة"
                }
        
        # حساب الاتجاه للمحاولات المتعددة
        first_half = grades[:len(grades)//2] if len(grades) > 2 else [grades[0]]
        second_half = grades[len(grades)//2:] if len(grades) > 2 else [grades[-1]]
        
        first_avg = statistics.mean(first_half)
        second_avg = statistics.mean(second_half)
        
        difference = second_avg - first_avg
        
        if difference > 5:
            trend = "متحسن"
            description = f"تحسن بمقدار {round(difference, 2)} نقطة"
        elif difference < -5:
            trend = "متراجع"
            description = f"تراجع بمقدار {round(abs(difference), 2)} نقطة"
        else:
            trend = "مستقر"
            description = "أداء مستقر نسبياً"
        
        return {
            "trend": trend,
            "difference": round(difference, 2),
            "description": description
        }
    
    @staticmethod
    def _identify_strengths_weaknesses(exam1_grades: List[float], exam2_grades: List[float], 
                                     coursework_grades: List[float]) -> Dict:
        """تحديد نقاط القوة والضعف في المادة"""
        exam1_avg = statistics.mean(exam1_grades)
        exam2_avg = statistics.mean(exam2_grades)
        coursework_avg = statistics.mean(coursework_grades)
        
        # تحديد أقوى وأضعف جانب
        components = {
            "الامتحان الأول": exam1_avg,
            "الامتحان الثاني": exam2_avg,
            "أعمال السنة": coursework_avg
        }
        
        strongest = max(components.keys(), key=lambda k: components[k])
        weakest = min(components.keys(), key=lambda k: components[k])
        
        return {
            "strongest_component": {
                "name": strongest,
                "average": round(components[strongest], 2),
                "percentage": round((components[strongest] / 30) * 100, 2) if strongest != "أعمال السنة" else round((components[strongest] / 90) * 100, 2)
            },
            "weakest_component": {
                "name": weakest,
                "average": round(components[weakest], 2),
                "percentage": round((components[weakest] / 30) * 100, 2) if weakest != "أعمال السنة" else round((components[weakest] / 90) * 100, 2)
            },
            "balance_analysis": AcademicStatusAnalysisService._analyze_component_balance(exam1_avg, exam2_avg, coursework_avg)
        }
    
    @staticmethod
    def _analyze_component_balance(exam1_avg: float, exam2_avg: float, coursework_avg: float) -> str:
        """تحليل توازن مكونات الدرجة"""
        # تحويل إلى نسب مئوية للمقارنة
        exam1_pct = (exam1_avg / 30) * 100
        exam2_pct = (exam2_avg / 30) * 100
        coursework_pct = (coursework_avg / 90) * 100
        
        variance = statistics.variance([exam1_pct, exam2_pct, coursework_pct])
        
        if variance < 50:
            return "أداء متوازن في جميع المكونات"
        elif coursework_pct > exam1_pct + 15 and coursework_pct > exam2_pct + 15:
            return "قوي في أعمال السنة، ضعيف في الامتحانات"
        elif exam1_pct > coursework_pct + 15 or exam2_pct > coursework_pct + 15:
            return "قوي في الامتحانات، ضعيف في أعمال السنة"
        else:
            return "أداء متفاوت بين المكونات"
    
    @staticmethod
    def _compare_with_class_average(student_avg: float, peer_avg: float) -> Dict:
        """مقارنة مفصلة مع متوسط الفصل"""
        difference = student_avg - peer_avg
        
        if difference > 15:
            status = "متفوق جداً"
            interpretation = f"أداؤك أعلى من المتوسط بـ {round(difference, 2)} نقطة - ممتاز!"
        elif difference > 10:
            status = "متفوق"
            interpretation = f"أداؤك أعلى من المتوسط بـ {round(difference, 2)} نقطة - جيد جداً"
        elif difference > 5:
            status = "أعلى من المتوسط"
            interpretation = f"أداؤك أعلى من المتوسط بـ {round(difference, 2)} نقطة"
        elif difference > -5:
            status = "قريب من المتوسط"
            interpretation = f"أداؤك قريب من المتوسط (فرق {round(abs(difference), 2)} نقطة)"
        elif difference > -10:
            status = "أقل من المتوسط"
            interpretation = f"أداؤك أقل من المتوسط بـ {round(abs(difference), 2)} نقطة - يحتاج تحسين"
        else:
            status = "أقل من المتوسط بشكل ملحوظ"
            interpretation = f"أداؤك أقل من المتوسط بـ {round(abs(difference), 2)} نقطة - يحتاج تحسين عاجل"
        
        return {
            "status": status,
            "difference": round(difference, 2),
            "interpretation": interpretation
        }
    
    @staticmethod
    def _generate_course_suggestions(detailed_analysis: Dict, comparison: Dict) -> List[str]:
        """توليد اقتراحات تحسين للمادة"""
        suggestions = []
        
        # اقتراحات حسب نقاط الضعف
        strengths_weaknesses = detailed_analysis.get("strengths_weaknesses", {})
        weakest = strengths_weaknesses.get("weakest_component", {})
        
        if weakest.get("name") == "الامتحان الأول":
            suggestions.append("ركز على التحضير المبكر للامتحان الأول")
        elif weakest.get("name") == "الامتحان الثاني":
            suggestions.append("حسن من استراتيجية المراجعة للامتحان النهائي")
        elif weakest.get("name") == "أعمال السنة":
            suggestions.append("اهتم أكثر بالواجبات والمشاركة الصفية")
        
        # اقتراحات حسب المقارنة مع الزملاء
        status = comparison.get("status", "")
        if "أقل من المتوسط" in status:
            suggestions.extend([
                "اطلب المساعدة من الأستاذ أو الزملاء المتفوقين",
                "خصص وقت إضافي لمراجعة هذه المادة"
            ])
        elif "قريب من المتوسط" in status:
            suggestions.append("جهد إضافي بسيط سيحسن ترتيبك كثيراً")
        
        # اقتراحات حسب الاتجاه
        trend = detailed_analysis.get("grade_trend", {}).get("trend", "")
        if trend == "متراجع":
            suggestions.append("راجع أسباب تراجع الأداء في هذه المادة")
        elif trend == "متحسن":
            suggestions.append("استمر على نفس النهج الناجح")
        
        return suggestions[:4]  # أقصى 4 اقتراحات
    
    @staticmethod
    def _generate_performance_summary(course_performance: Dict) -> Dict:
        """توليد ملخص الأداء العام"""
        if not course_performance:
            return {"error": "No course data available"}
        
        # جمع البيانات
        all_averages = []
        strong_courses = []
        weak_courses = []
        improving_courses = []
        declining_courses = []
        
        for course_key, data in course_performance.items():
            avg = data["detailed_analysis"]["overall_average"]
            all_averages.append(avg)
            
            # تصنيف المواد
            if avg >= 80:
                strong_courses.append({"name": data["course_name"], "average": avg})
            elif avg < 60:
                weak_courses.append({"name": data["course_name"], "average": avg})
            
            # تحليل الاتجاه
            trend = data["detailed_analysis"]["grade_trend"]["trend"]
            if trend == "متحسن":
                improving_courses.append(data["course_name"])
            elif trend == "متراجع":
                declining_courses.append(data["course_name"])
        
        # حساب الإحصائيات العامة
        overall_average = round(statistics.mean(all_averages), 2)
        
        return {
            "overall_average": overall_average,
            "performance_level": AcademicStatusAnalysisService._classify_performance_level(overall_average),
            "strong_courses": strong_courses[:3],  # أفضل 3 مواد
            "weak_courses": weak_courses[:3],      # أضعف 3 مواد
            "improving_courses": improving_courses,
            "declining_courses": declining_courses,
            "total_courses_analyzed": len(course_performance)
        }
    
    @staticmethod
    def _classify_performance_level(average: float) -> str:
        """تصنيف مستوى الأداء"""
        if average >= 85:
            return "ممتاز"
        elif average >= 75:
            return "جيد جداً"
        elif average >= 65:
            return "جيد"
        elif average >= 50:
            return "مقبول"
        else:
            return "ضعيف"
    
    @staticmethod
    def _generate_overall_course_insights(course_performance: Dict) -> List[str]:
        """توليد رؤى عامة حول أداء المواد"""
        insights = []
        
        if not course_performance:
            return ["لا توجد بيانات كافية للتحليل"]
        
        # تحليل التوازن بين المواد
        averages = [data["detailed_analysis"]["overall_average"] for data in course_performance.values()]
        variance = statistics.variance(averages) if len(averages) > 1 else 0
        
        if variance < 100:
            insights.append("أداؤك متوازن نسبياً بين المواد المختلفة")
        else:
            insights.append("هناك تفاوت كبير في أداؤك بين المواد - ركز على المواد الضعيفة")
        
        # تحليل نقاط القوة والضعف العامة
        exam_strengths = 0
        coursework_strengths = 0
        
        for data in course_performance.values():
            strongest = data["detailed_analysis"]["strengths_weaknesses"]["strongest_component"]["name"]
            if "امتحان" in strongest:
                exam_strengths += 1
            else:
                coursework_strengths += 1
        
        if exam_strengths > coursework_strengths:
            insights.append("نقطة قوتك في الامتحانات - حاول تحسين أعمال السنة")
        elif coursework_strengths > exam_strengths:
            insights.append("نقطة قوتك في أعمال السنة - ركز على تحسين أداء الامتحانات")
        else:
            insights.append("أداؤك متوازن بين الامتحانات وأعمال السنة")
        
        return insights
    
    @staticmethod
    def _analyze_attendance_patterns(student_id: int) -> Dict:
        """تحليل مبسط للحضور"""
        try:
            # حساب معدل الحضور من دالة موجودة
            attendance_rate = AcademicStatusAnalysisService._calculate_attendance_rate(student_id)
            
            # تحديد حالة الحضور
            if attendance_rate >= 0.9:
                status = "ممتاز"
                description = "حضور منتظم ومتميز"
            elif attendance_rate >= 0.8:
                status = "جيد"
                description = "حضور جيد مع بعض الغيابات"
            elif attendance_rate >= 0.7:
                status = "مقبول"
                description = "حضور مقبول لكن يحتاج تحسين"
            else:
                status = "ضعيف"
                description = "حضور ضعيف يحتاج تدخل فوري"
            
            return {
                "attendance_rate": round(attendance_rate, 2),
                "status": status,
                "description": description
            }
            
        except Exception as e:
            return {
                "attendance_rate": 0.0,
                "status": "غير متوفر",
                "description": "لا توجد بيانات حضور كافية"
            }
    
    @staticmethod
    def _get_warnings_summary(student_id: int) -> Dict:
        """ملخص سريع للإنذارات الأكاديمية"""
        try:
            # البحث عن الإنذارات في جدول AcademicWarnings
            warnings = AcademicWarnings.query.filter_by(StudentId=student_id).all()
            
            if not warnings:
                return {
                    "total_warnings": 0,
                    "active_warnings_count": 0,
                    "current_status": "لا توجد إنذارات",
                    "risk_level": "آمن",
                    "last_warning_date": None
                }
            
            # حساب الإنذارات النشطة
            active_warnings_count = 0
            last_warning_date = None
            
            for warning in warnings:
                is_resolved = getattr(warning, 'IsResolved', False)
                if not is_resolved:
                    active_warnings_count += 1
                
                # تحديث تاريخ آخر إنذار
                if warning.IssueDate:
                    if last_warning_date is None or warning.IssueDate > last_warning_date:
                        last_warning_date = warning.IssueDate
            
            total_warnings = len(warnings)
            
            # تحديد مستوى المخاطرة والحالة الحالية
            if active_warnings_count == 0:
                risk_level = "آمن"
                current_status = f"تم حل جميع الإنذارات ({total_warnings} إنذار سابق)" if total_warnings > 0 else "لا توجد إنذارات"
            elif active_warnings_count == 1:
                risk_level = "تحذير"
                current_status = "إنذار واحد نشط"
            elif active_warnings_count == 2:
                risk_level = "خطر"
                current_status = "إنذاران نشطان"
            else:
                risk_level = "خطر شديد"
                current_status = f"{active_warnings_count} إنذارات نشطة - مهدد بالفصل"
            
            return {
                "total_warnings": total_warnings,
                "active_warnings_count": active_warnings_count,
                "current_status": current_status,
                "risk_level": risk_level,
                "last_warning_date": last_warning_date.isoformat() if last_warning_date else None
            }
            
        except Exception as e:
            return {"error": f"Warnings summary failed: {str(e)}"}
    
    @staticmethod
    def _compare_with_peers(student_id: int) -> Dict:
        """مقارنة مبسطة للطالب مع زملائه في نفس الشعبة والترم"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            # الحصول على معلومات الطالب الأساسية
            student_division = student.DivisionId
            student_semester = student.Semester
            student_current_gpa = AcademicStatusAnalysisService._get_current_gpa(student)
            
            # جلب الطلاب في نفس الشعبة والترم
            peers = Students.query.filter(
                Students.DivisionId == student_division,
                Students.Semester == student_semester,
                Students.Id != student_id
            ).all()
            
            if not peers:
                return {
                    "student_info": {
                        "rank": 1,
                        "total_students": 1
                    },
                    "division_stats": {
                        "average_gpa": student_current_gpa,
                        "highest_gpa": student_current_gpa,
                        "lowest_gpa": student_current_gpa
                    },
                    "performance_analysis": {
                        "level": "غير محدد",
                        "description": "لا يوجد طلاب آخرون للمقارنة",
                        "gpa_difference_from_average": 0
                    },
                    "recommendations": [
                        "المحافظة على الأداء الحالي",
                        "مراقبة المعدل التراكمي بانتظام"
                    ]
                }
            
            # حساب المعدلات التراكمية للزملاء
            peer_gpas = []
            peer_data = []
            
            for peer in peers:
                peer_gpa = AcademicStatusAnalysisService._get_current_gpa(peer)
                if peer_gpa > 0:  # تجاهل الطلاب بدون معدل
                    peer_gpas.append(peer_gpa)
                    peer_data.append({
                        "student_id": peer.Id,
                        "name": peer.Name,
                        "gpa": peer_gpa
                    })
            
            if not peer_gpas:
                return {
                    "student_info": {
                        "rank": 1,
                        "total_students": 1
                    },
                    "division_stats": {
                        "average_gpa": student_current_gpa,
                        "highest_gpa": student_current_gpa,
                        "lowest_gpa": student_current_gpa
                    },
                    "performance_analysis": {
                        "level": "غير محدد",
                        "description": "لا توجد معدلات صالحة للمقارنة",
                        "gpa_difference_from_average": 0
                    },
                    "recommendations": [
                        "المحافظة على الأداء الحالي",
                        "مراقبة المعدل التراكمي بانتظام"
                    ]
                }
            
            # إضافة الطالب الحالي للقائمة لحساب الترتيب
            all_students_data = peer_data + [{
                "student_id": student.Id,
                "name": student.Name,
                "gpa": student_current_gpa
            }]
            
            # ترتيب الطلاب حسب المعدل التراكمي (من الأعلى للأقل)
            all_students_data.sort(key=lambda x: x["gpa"], reverse=True)
            
            # العثور على ترتيب الطالب
            student_rank = None
            for i, student_data in enumerate(all_students_data):
                if student_data["student_id"] == student.Id:
                    student_rank = i + 1
                    break
            
            # حساب الإحصائيات
            total_students = len(all_students_data)
            average_gpa = statistics.mean(peer_gpas)
            max_gpa = max(peer_gpas)
            min_gpa = min(peer_gpas)
            
            # تحديد الأداء النسبي
            if student_current_gpa >= average_gpa + 0.5:
                performance_level = "ممتاز"
                performance_description = "أعلى من المتوسط بشكل ملحوظ"
            elif student_current_gpa >= average_gpa:
                performance_level = "جيد"
                performance_description = "أعلى من المتوسط"
            elif student_current_gpa >= average_gpa - 0.3:
                performance_level = "متوسط"
                performance_description = "قريب من المتوسط"
            else:
                performance_level = "ضعيف"
                performance_description = "أقل من المتوسط"
            
            # توصيات بناءً على الأداء
            recommendations = []
            if performance_level == "ممتاز":
                recommendations = [
                    "المحافظة على الأداء المتميز",
                    "مساعدة الزملاء الأقل أداءً",
                    "التفكير في أنشطة إضافية أو بحثية"
                ]
            elif performance_level == "جيد":
                recommendations = [
                    "السعي للوصول للمراتب الأولى",
                    "تحسين الأداء في المواد الضعيفة",
                    "المشاركة في مجموعات الدراسة"
                ]
            elif performance_level == "متوسط":
                recommendations = [
                    "وضع خطة لتحسين المعدل التراكمي",
                    "تحديد نقاط الضعف ومعالجتها",
                    "زيادة ساعات الدراسة"
                ]
            else:
                recommendations = [
                    "تدخل أكاديمي فوري مطلوب",
                    "مراجعة شاملة لطريقة الدراسة",
                    "طلب الدعم من المرشد الأكاديمي"
                ]
            
            return {
                "student_info": {
                    "rank": student_rank,
                    "total_students": total_students
                },
                "division_stats": {
                    "average_gpa": round(average_gpa, 2),
                    "highest_gpa": round(max_gpa, 2),
                    "lowest_gpa": round(min_gpa, 2)
                },
                "performance_analysis": {
                    "level": performance_level,
                    "description": performance_description,
                    "gpa_difference_from_average": round(student_current_gpa - average_gpa, 2)
                },
                "recommendations": recommendations
            }
            
        except Exception as e:
            return {"error": f"Peer comparison failed: {str(e)}"}
    
    @staticmethod
    def _compare_gpa(current_gpa: float, peer_gpa_history: List[float]) -> str:
        """مقارنة المعدل التراكمي للطالب مع المعدلات التراكمية للطلاب الآخرين"""
        if current_gpa < 2.0:
            return "أقل من الحد الادنى"
        elif current_gpa < 3.0:
            return "متوسط"
        else:
            return "ممتاز"
    
    @staticmethod
    def _interpret_gpa_comparison(comparison_type: str, current_gpa: float, peer_gpa_history: List[float]) -> str:
        """تفسير نتيجة المقارنة"""
        if comparison_type == "أقل من المتوسط":
            return f"أداء الطالب أقل من المتوسط (معدل التراكمي: {current_gpa:.2f})"
        elif comparison_type == "متوسط":
            return f"أداء الطالب متوسط (معدل التراكمي: {current_gpa:.2f})"
        else:
            return f"أداء الطالب أعلى المتوسط (معدل التراكمي: {current_gpa:.2f})"

    @staticmethod
    def _get_merged_predictions(student_id: int) -> Dict:
        """توقع أداء الطالب المدمج"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            # الطالب في الترم X يعني أنه أكمل الترم X-1
            completed_semester = student.Semester - 1
            
            if completed_semester <= 0:
                return {
                    "prediction_type": "insufficient_data",
                    "predicted_gpa": None,
                    "current_gpa": 0,
                    "confidence": 0,
                    "risk_level": "unknown",
                    "gpa_trend": 0,
                    "interpretation": "الطالب لم يكمل أي فصل دراسي بعد"
                }
            
            # جمع المعدلات التراكمية
            cumulative_gpas = []
            total_gpa = 0.0
            
            for i in range(1, completed_semester + 1):
                semester_gpa = getattr(student, f'GPA{i}', None)
                if semester_gpa is not None:
                    total_gpa += float(semester_gpa)
                    cumulative_gpa = total_gpa / i
                    cumulative_gpas.append(cumulative_gpa)
            
            if len(cumulative_gpas) < 2:
                current_gpa = cumulative_gpas[0] if cumulative_gpas else 0
                return {
                    "prediction_type": "insufficient_data",
                    "predicted_gpa": current_gpa,
                    "current_gpa": current_gpa,
                    "confidence": 30,
                    "risk_level": "unknown",
                    "gpa_trend": 0,
                    "interpretation": "بيانات غير كافية للتنبؤ الدقيق"
                }
            
            # حساب التوقع باستخدام الانحدار الخطي
            X = np.array(range(1, len(cumulative_gpas) + 1)).reshape(-1, 1)
            y = np.array(cumulative_gpas)
            
            model = LinearRegression()
            model.fit(X, y)
            predicted_gpa = model.predict(np.array([[len(cumulative_gpas) + 1]]))[0]
            
            # تحديد مستوى المخاطرة والاتجاه
            current_gpa = cumulative_gpas[-1]
            gpa_trend = predicted_gpa - current_gpa
            
            if current_gpa < 2.0 or predicted_gpa < 2.0:
                risk_level = "عالي"
            elif current_gpa < 2.5 or (predicted_gpa < 2.5 and gpa_trend < 0):
                risk_level = "متوسط"
            else:
                risk_level = "منخفض"
            
            # تحديد نوع التوقع
            if predicted_gpa < 2.0:
                prediction_type = "حرج"
            elif predicted_gpa < 2.5:
                prediction_type = "تحذير"
            elif predicted_gpa < 3.0:
                prediction_type = "متوسط"
            else:
                prediction_type = "ممتاز"
            
            # حساب مستوى الثقة
            confidence = min(100, max(50, len(cumulative_gpas) * 15))
            
            # تفسير شامل
            interpretation = f"التوقع: معدل تراكمي {predicted_gpa:.2f} - "
            
            if prediction_type == "حرج":
                interpretation += "وضع حرج يتطلب تدخل فوري"
            elif prediction_type == "تحذير":
                interpretation += "تحذير: يحتاج تحسين عاجل"
            elif prediction_type == "متوسط":
                interpretation += "أداء متوسط"
            else:
                interpretation += "أداء ممتاز"
            
            if gpa_trend > 0.1:
                interpretation += " مع اتجاه متحسن"
            elif gpa_trend < -0.1:
                interpretation += " مع اتجاه متراجع"
            else:
                interpretation += " مع استقرار نسبي"
            
            return {
                "prediction_type": prediction_type,
                "predicted_gpa": round(predicted_gpa, 2),
                "current_gpa": round(current_gpa, 2),
                "confidence": confidence,
                "risk_level": risk_level,
                "gpa_trend": round(gpa_trend, 3),
                "gpa_history": [round(gpa, 2) for gpa in cumulative_gpas],
                "interpretation": interpretation
            }
            
        except Exception as e:
            return {"error": f"Merged predictions failed: {str(e)}"}
    
    @staticmethod
    def _predictive_intervention_system(student_id: int) -> Dict:
        """نظام التدخل التنبؤي المبسط"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            current_gpa = AcademicStatusAnalysisService._get_current_gpa(student)
            risk_assessment = AcademicStatusAnalysisService._calculate_risk_assessment(student_id)
            future_prediction = AcademicStatusAnalysisService._get_merged_predictions(student_id)
            
            # تحديد التدخل الأساسي بناءً على المعدل ومستوى المخاطرة
            intervention = {}
            
            if current_gpa < 2.0:
                intervention = {
                    "type": "فوري",
                    "priority": "عاجل",
                    "title": "تدخل أكاديمي فوري",
                    "description": "المعدل التراكمي أقل من 2.0 - يحتاج تدخل فوري",
                    "key_actions": [
                        "مقابلة المرشد الأكاديمي فوراً",
                        "وضع خطة تحسين مكثفة",
                        "الحصول على دعم أكاديمي إضافي"
                    ]
                }
            elif current_gpa < 2.5 or risk_assessment.get("risk_level") in ["متوسط", "عالي"]:
                intervention = {
                    "type": "وقائي",
                    "priority": "مهم",
                    "title": "تدخل وقائي",
                    "description": "مؤشرات تدل على احتمالية تراجع الأداء",
                    "key_actions": [
                        "مراجعة الخطة الدراسية",
                        "تحسين عادات الدراسة",
                        "طلب المساعدة في المواد الصعبة"
                    ]
                }
            elif current_gpa >= 3.0:
                intervention = {
                    "type": "تطويري",
                    "priority": "تطويري",
                    "title": "تطوير الأداء",
                    "description": "فرص لتحسين الأداء الجيد أكثر",
                    "key_actions": [
                        "التحدي بمواد متقدمة",
                        "المشاركة في الأنشطة البحثية",
                        "تطوير مهارات القيادة"
                    ]
                }
            else:
                intervention = {
                    "type": "عام",
                    "priority": "متوسط",
                    "title": "تحسين الأداء العام",
                    "description": "توصيات عامة لتحسين الأداء الأكاديمي",
                    "key_actions": [
                        "تنظيم الوقت بشكل أفضل",
                        "المراجعة المنتظمة للمواد",
                        "المشاركة في المجموعات الدراسية"
                    ]
                }
            
            # تقييم فعالية التدخل المتوقعة
            effectiveness_score = AcademicStatusAnalysisService._calculate_intervention_effectiveness(
                current_gpa, risk_assessment, [intervention]
            )
            
            return {
                "intervention": intervention,
                "current_risk_level": risk_assessment.get("risk_level", "unknown"),
                "predicted_outcome": future_prediction.get("prediction_type", "unknown"),
                "effectiveness_score": effectiveness_score
            }
            
        except Exception as e:
            return {"error": f"Predictive intervention system failed: {str(e)}"}

    @staticmethod
    def _calculate_intervention_effectiveness(current_gpa: float, risk_assessment: Dict, 
                                           interventions: List[Dict]) -> int:
        """حساب فعالية التدخل المتوقعة"""
        try:
            base_score = 50
            
            # تعديل النتيجة بناءً على المعدل الحالي
            if current_gpa >= 3.0:
                base_score += 20
            elif current_gpa >= 2.5:
                base_score += 10
            elif current_gpa < 2.0:
                base_score -= 20
            
            # تعديل النتيجة بناءً على مستوى المخاطرة
            risk_level = risk_assessment.get("risk_level", "unknown")
            if risk_level == "منخفض":
                base_score += 15
            elif risk_level == "عالي":
                base_score -= 15
            
            # تعديل النتيجة بناءً على عدد التدخلات
            intervention_count = len(interventions)
            if intervention_count > 1:
                base_score += min(10, intervention_count * 3)
            
            return max(0, min(100, base_score))
            
        except Exception:
            return 50
    
    @staticmethod
    def _generate_personalized_learning_path(student_id: int) -> Dict:
        """مسار تعلم شخصي"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            # الحصول على المعدل التراكمي الحالي
            current_gpa = AcademicStatusAnalysisService._get_current_gpa(student)
            
            # تحليل نقاط القوة والضعف
            enrollments = Enrollments.query.filter_by(StudentId=student_id).all()
            course_performance = AcademicStatusAnalysisService._analyze_course_performance(student_id)
            
            # تحديد المسار بناءً على الأداء
            if current_gpa >= 3.5:
                learning_path = "مسار التميز"
                recommendations = [
                    "التحدي بمواد متقدمة",
                    "المشاركة في الأنشطة البحثية",
                    "تطوير مهارات القيادة",
                    "التفكير في التخصص المزدوج"
                ]
            elif current_gpa >= 3.0:
                learning_path = "مسار التطوير"
                recommendations = [
                    "التركيز على المواد الأساسية",
                    "تحسين المهارات الدراسية",
                    "المشاركة في مجموعات الدراسة",
                    "البحث عن فرص التدريب"
                ]
            elif current_gpa >= 2.0:
                learning_path = "مسار التحسين"
                recommendations = [
                    "مراجعة الأساسيات",
                    "تقليل العبء الدراسي",
                    "طلب المساعدة الأكاديمية",
                    "تطوير عادات دراسية أفضل"
                ]
            else:
                learning_path = "مسار الإنقاذ"
                recommendations = [
                    "التركيز على المواد الأساسية فقط",
                    "الحصول على دعم أكاديمي مكثف",
                    "إعادة تقييم الخطة الدراسية",
                    "التفكير في تغيير التخصص إذا لزم الأمر"
                ]
            
            return {
                "learning_path": learning_path,
                "current_gpa": current_gpa,
                "recommendations": recommendations,
                "focus_areas": AcademicStatusAnalysisService._identify_focus_areas(course_performance),
                "timeline": AcademicStatusAnalysisService._generate_timeline(student.Semester, current_gpa)
            }
            
        except Exception as e:
            return {"error": f"Personalized learning path generation failed: {str(e)}"}

    @staticmethod
    def _identify_focus_areas(course_performance: Dict) -> List[str]:
        """تحديد مجالات التركيز"""
        focus_areas = []
        
        try:
            if "course_performance" in course_performance:
                performances = course_performance["course_performance"]
                
                # تحديد المواد التي تحتاج تحسين
                weak_courses = []
                for course_key, data in performances.items():
                    if data["detailed_analysis"]["overall_average"] < 70:  # أقل من 70%
                        weak_courses.append(data["course_name"])
                
                if weak_courses:
                    focus_areas.append(f"تحسين الأداء في: {', '.join(weak_courses[:3])}")
                
                # تحديد المواد القوية للبناء عليها
                strong_courses = []
                for course_key, data in performances.items():
                    if data["detailed_analysis"]["overall_average"] >= 85:  # 85% فأكثر
                        strong_courses.append(data["course_name"])
                
                if strong_courses:
                    focus_areas.append(f"البناء على نقاط القوة في: {', '.join(strong_courses[:2])}")
            
            if not focus_areas:
                focus_areas.append("تطوير مهارات الدراسة العامة")
            
            return focus_areas
            
        except Exception:
            return ["مراجعة شاملة للأداء الأكاديمي"]

    @staticmethod
    def _generate_timeline(current_semester: int, current_gpa: float) -> Dict:
        """توليد جدول زمني للتحسين"""
        try:
            remaining_semesters = max(1, 8 - current_semester + 1)
            
            if current_gpa >= 3.5:
                timeline = {
                    "short_term": "الحفاظ على التميز في الفصل الحالي",
                    "medium_term": f"تطوير مهارات متقدمة خلال {min(2, remaining_semesters)} فصول",
                    "long_term": "التحضير للدراسات العليا أو سوق العمل"
                }
            elif current_gpa >= 3.0:
                timeline = {
                    "short_term": "تحسين المعدل بـ 0.2 نقطة في الفصل الحالي",
                    "medium_term": f"الوصول لمعدل 3.5 خلال {min(3, remaining_semesters)} فصول",
                    "long_term": "تحقيق التميز الأكاديمي"
                }
            elif current_gpa >= 2.0:
                timeline = {
                    "short_term": "تجنب الإنذار الأكاديمي في الفصل الحالي",
                    "medium_term": f"الوصول لمعدل 3.0 خلال {min(4, remaining_semesters)} فصول",
                    "long_term": "تحقيق الاستقرار الأكاديمي"
                }
            else:
                timeline = {
                    "short_term": "رفع المعدل فوق 2.0 فوراً",
                    "medium_term": "تجنب الفصل الأكاديمي",
                    "long_term": "إعادة بناء الأداء الأكاديمي"
                }
            
            return timeline
            
        except Exception:
            return {
                "short_term": "التركيز على الفصل الحالي",
                "medium_term": "تحسين الأداء تدريجياً",
                "long_term": "تحقيق الأهداف الأكاديمية"
            }

    @staticmethod
    def _generate_ai_insights(student_id: int) -> Dict:
        """توليد تلميحات AI"""
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            # جمع البيانات للتحليل
            current_gpa = AcademicStatusAnalysisService._get_current_gpa(student)
            gpa_trends = AcademicStatusAnalysisService._analyze_gpa_trends(student_id)
            course_performance = AcademicStatusAnalysisService._analyze_course_performance(student_id)
            risk_assessment = AcademicStatusAnalysisService._calculate_risk_assessment(student_id)
            
            # توليد الرؤى الذكية
            insights = []
            
            # رؤى المعدل التراكمي
            if current_gpa >= 3.5:
                insights.append({
                    "type": "positive",
                    "title": "أداء متميز",
                    "description": f"معدلك التراكمي {current_gpa} يضعك في المرتبة الممتازة",
                    "action": "حافظ على هذا المستوى وفكر في التحديات الإضافية"
                })
            elif current_gpa >= 3.0:
                insights.append({
                    "type": "neutral",
                    "title": "أداء جيد",
                    "description": f"معدلك التراكمي {current_gpa} جيد ولكن يمكن تحسينه",
                    "action": "ركز على المواد الضعيفة لرفع المعدل"
                })
            else:
                insights.append({
                    "type": "warning",
                    "title": "يحتاج تحسين",
                    "description": f"معدلك التراكمي {current_gpa} يحتاج تحسين عاجل",
                    "action": "راجع استراتيجية الدراسة واطلب المساعدة"
                })
            
            # رؤى الاتجاه
            if gpa_trends.get("trend") == "متحسن":
                insights.append({
                    "type": "positive",
                    "title": "تحسن مستمر",
                    "description": "أداؤك يتحسن باستمرار",
                    "action": "استمر على نفس النهج"
                })
            elif gpa_trends.get("trend") == "متراجع":
                insights.append({
                    "type": "warning",
                    "title": "تراجع في الأداء",
                    "description": "هناك تراجع في أداؤك الأكاديمي",
                    "action": "حدد أسباب التراجع وضع خطة للتحسين"
                })
            
            # رؤى المواد
            if "course_performance" in course_performance:
                performances = course_performance["course_performance"]
                weak_courses = [data["course_name"] for data in performances.values() 
                              if data["detailed_analysis"]["overall_average"] < 70]
                
                if weak_courses:
                    insights.append({
                        "type": "info",
                        "title": "مواد تحتاج تركيز",
                        "description": f"المواد التالية تحتاج تحسين: {', '.join(weak_courses[:3])}",
                        "action": "خصص وقت إضافي لهذه المواد"
                    })
            
            # رؤى المخاطر
            risk_level = risk_assessment.get("risk_level", "منخفض")
            if risk_level == "عالي":
                insights.append({
                    "type": "critical",
                    "title": "تحذير عاجل",
                    "description": "وضعك الأكاديمي يتطلب تدخل فوري",
                    "action": "قابل المرشد الأكاديمي فوراً"
                })
            
            return {
                "insights": insights,
                "total_insights": len(insights),
                "priority_level": AcademicStatusAnalysisService._determine_priority_level(insights),
                "summary": AcademicStatusAnalysisService._generate_insights_summary(insights)
            }
            
        except Exception as e:
            return {"error": f"AI insights generation failed: {str(e)}"}
    
    @staticmethod
    def _determine_priority_level(insights: List[Dict]) -> str:
        """تحديد مستوى الأولوية"""
        if any(insight["type"] == "critical" for insight in insights):
            return "عاجل"
        elif any(insight["type"] == "warning" for insight in insights):
            return "مهم"
        elif any(insight["type"] == "positive" for insight in insights):
            return "إيجابي"
        else:
            return "عادي"

    @staticmethod
    def _generate_insights_summary(insights: List[Dict]) -> str:
        """توليد ملخص الرؤى"""
        if not insights:
            return "لا توجد رؤى متاحة"
        
        critical_count = sum(1 for insight in insights if insight["type"] == "critical")
        warning_count = sum(1 for insight in insights if insight["type"] == "warning")
        positive_count = sum(1 for insight in insights if insight["type"] == "positive")
        
        if critical_count > 0:
            return f"يوجد {critical_count} تحذير عاجل يتطلب انتباه فوري"
        elif warning_count > 0:
            return f"يوجد {warning_count} تحذير يحتاج متابعة"
        elif positive_count > 0:
            return f"أداء إيجابي مع {positive_count} نقطة قوة"
        else:
            return "الوضع الأكاديمي مستقر"

    @staticmethod
    def _get_current_gpa(student: Students) -> float:
        """الحصول على المعدل التراكمي الحالي للطالب"""
        try:
           
            completed_semester = student.Semester - 1  # آخر ترم مكتمل
            
            if completed_semester <= 0:
                return 0.0
            
            # جمع معدلات جميع الترمات المكتملة
            total_gpa = 0.0
            valid_semesters = 0
            
            for i in range(1, completed_semester + 1):
                semester_gpa = getattr(student, f'GPA{i}', None)
                if semester_gpa is not None:
                    total_gpa += float(semester_gpa)
                    valid_semesters += 1
            
            # حساب المعدل التراكمي
            if valid_semesters > 0:
                return round(total_gpa / valid_semesters, 2)
            
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _calculate_gpa_trend(enrollments: List) -> Dict:
        """حساب اتجاه المعدل التراكمي"""
        try:
            if not enrollments:
                return {"trend": "no_data", "slope": 0}
            
            # جمع المعدلات حسب الفصل وحساب المعدل التراكمي لكل فصل
            semester_gpas = {}
            for enrollment in enrollments:
                if enrollment.Grade is not None and enrollment.Exam1Grade is not None and enrollment.Exam2Grade is not None:
                    # حساب الدرجة الإجمالية من 150 (30+30+90)
                    total_grade = float(enrollment.Exam1Grade) + float(enrollment.Exam2Grade) + float(enrollment.Grade)
                    # تحويل إلى نظام 4.0
                    gpa_grade = (total_grade / 150.0) * 4.0
                    
                    semester = enrollment.Semester
                    if semester not in semester_gpas:
                        semester_gpas[semester] = []
                    semester_gpas[semester].append(gpa_grade)
            
            # حساب المعدل التراكمي لكل فصل
            cumulative_gpas = []
            semesters = sorted(semester_gpas.keys())
            
            for i, semester in enumerate(semesters):
                # حساب المعدل التراكمي حتى هذا الفصل
                total_gpa = 0.0
                total_courses = 0
                
                for j in range(i + 1):
                    semester_courses = semester_gpas[semesters[j]]
                    total_gpa += sum(semester_courses)
                    total_courses += len(semester_courses)
                
                if total_courses > 0:
                    cumulative_gpa = total_gpa / total_courses
                    cumulative_gpas.append(cumulative_gpa)
            
            if len(cumulative_gpas) < 2:
                return {"trend": "insufficient_data", "slope": 0}
            
            # حساب الاتجاه باستخدام الانحدار الخطي
            X = np.array(range(len(cumulative_gpas))).reshape(-1, 1)
            y = np.array(cumulative_gpas)
            
            model = LinearRegression()
            model.fit(X, y)
            slope = model.coef_[0]
            
            if slope > 0.1:
                trend = "متحسن"
            elif slope < -0.1:
                trend = "متراجع"
            else:
                trend = "مستقر"
            return {
                "trend": trend,
                "slope": round(slope, 3),
                "cumulative_gpas": [round(gpa, 2) for gpa in cumulative_gpas],
                "semesters": semesters
            }
            
        except Exception as e:
            return {"trend": "error", "slope": 0, "error": str(e)}
    
    @staticmethod
    def _calculate_grade_variance(enrollments: List) -> float:
        """حساب تباين الدرجات"""
        try:
            grades = []
            for e in enrollments:
                if (e.Grade is not None and 
                    e.Exam1Grade is not None and 
                    e.Exam2Grade is not None):
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(e.Exam1Grade) + 
                                 float(e.Exam2Grade) + 
                                 float(e.Grade))
                    # تحويل إلى نسبة مئوية
                    percentage = (total_grade / 150.0) * 100
                    grades.append(percentage)
            
            if len(grades) < 2:
                return 0.0
            return statistics.variance(grades)
        except Exception:
            return 0.0

    @staticmethod
    def _calculate_completion_rate(enrollments: List) -> float:
        """حساب معدل إكمال المواد"""
        try:
            if not enrollments:
                return 0.0
            
            completed = sum(1 for e in enrollments if e.Status == 'Completed')
            total = len(enrollments)
            
            return completed / total if total > 0 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _calculate_enrollment_consistency(enrollments: List) -> Dict:
        """حساب اتساق التسجيل"""
        try:
            if not enrollments:
                return {"consistency": "no_data", "score": 0}
            
            # تحليل التسجيل حسب الفصل
            semester_enrollments = {}
            for enrollment in enrollments:
                semester = enrollment.Semester
                if semester not in semester_enrollments:
                    semester_enrollments[semester] = 0
                semester_enrollments[semester] += 1
            
            if len(semester_enrollments) < 2:
                return {"consistency": "insufficient_data", "score": 0}
            
            # حساب التباين في عدد المواد المسجلة
            enrollment_counts = list(semester_enrollments.values())
            variance = statistics.variance(enrollment_counts)
            
            if variance < 1:
                consistency = "high"
                score = 90
            elif variance < 4:
                consistency = "medium"
                score = 70
            else:
                consistency = "low"
                score = 40
            
            return {
                "consistency": consistency,
                "score": score,
                "variance": round(variance, 2),
                "semester_enrollments": semester_enrollments
            }
            
        except Exception as e:
            return {"consistency": "error", "score": 0, "error": str(e)}
    
    @staticmethod
    def _analyze_difficulty_preference(enrollments: List) -> Dict:
        """تحليل تفضيل صعوبة المواد"""
        try:
            if not enrollments:
                return {"preference": "no_data", "analysis": {}}
            
            # تصنيف المواد حسب الساعات المعتمدة (مؤشر على الصعوبة)
            difficulty_performance = {"easy": [], "medium": [], "hard": []}
            
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None and
                    hasattr(enrollment, 'course') and enrollment.course):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    credits = enrollment.course.Credits
                    
                    if credits <= 2:
                        difficulty_performance["easy"].append(percentage)
                    elif credits <= 3:
                        difficulty_performance["medium"].append(percentage)
                    else:
                        difficulty_performance["hard"].append(percentage)
            
            # حساب متوسط الأداء لكل مستوى صعوبة
            analysis = {}
            for difficulty, grades in difficulty_performance.items():
                if grades:
                    analysis[difficulty] = {
                        "average_grade": round(statistics.mean(grades), 2),
                        "count": len(grades),
                        "best_grade": max(grades),
                        "worst_grade": min(grades)
                    }
            
            # تحديد التفضيل
            if analysis:
                best_difficulty = max(analysis.keys(), 
                                    key=lambda k: analysis[k]["average_grade"])
                preference = best_difficulty
            else:
                preference = "no_data"
            
            return {
                "preference": preference,
                "analysis": analysis,
                "recommendation": f"الطالب يؤدي بشكل أفضل في المواد {preference}"
            }
            
        except Exception as e:
            return {"preference": "error", "analysis": {}, "error": str(e)}
    
    @staticmethod
    def _calculate_average_completion_time(enrollments: List) -> Dict:
        """حساب متوسط وقت إكمال المواد"""
        try:
            if not enrollments:
                return {"average_time": 0, "analysis": "no_data"}
            
            completion_times = []
            for enrollment in enrollments:
                if (enrollment.Status == 'Completed' and 
                    hasattr(enrollment, 'StartDate') and 
                    hasattr(enrollment, 'EndDate') and
                    enrollment.StartDate and enrollment.EndDate):
                    
                    time_diff = enrollment.EndDate - enrollment.StartDate
                    completion_times.append(time_diff.days)
            
            if not completion_times:
                return {"average_time": 0, "analysis": "no_completion_data"}
            
            average_time = statistics.mean(completion_times)
            
            # تحليل الوقت
            if average_time <= 90:  # 3 أشهر
                analysis = "سريع في إكمال المواد"
            elif average_time <= 120:  # 4 أشهر
                analysis = "متوسط في إكمال المواد"
            else:
                analysis = "بطيء في إكمال المواد"
            
            return {
                "average_time": round(average_time, 1),
                "analysis": analysis,
                "total_courses": len(completion_times),
                "fastest": min(completion_times),
                "slowest": max(completion_times)
            }
            
        except Exception as e:
            return {"average_time": 0, "analysis": "error", "error": str(e)}

    @staticmethod
    def _identify_success_factors(features: Dict) -> List[str]:
        """تحديد عوامل النجاح"""
        success_factors = []
        
        try:
            # تحليل المعدل التراكمي
            if features.get("current_gpa", 0) >= 3.5:
                success_factors.append("معدل تراكمي ممتاز")
            elif features.get("current_gpa", 0) >= 3.0:
                success_factors.append("معدل تراكمي جيد")
            
            # تحليل الاتجاه
            if features.get("gpa_trend", {}).get("trend") == "متحسن":
                success_factors.append("تحسن مستمر في الأداء")
            
            # تحليل معدل الحضور
            if features.get("attendance_rate", 0) >= 0.9:
                success_factors.append("انتظام ممتاز في الحضور")
            elif features.get("attendance_rate", 0) >= 0.8:
                success_factors.append("انتظام جيد في الحضور")
            
            # تحليل معدل الإكمال
            if features.get("completion_rate", 0) >= 0.9:
                success_factors.append("معدل إكمال ممتاز للمواد")
            
            # تحليل الاتساق
            consistency = features.get("enrollment_consistency", {})
            if consistency.get("consistency") == "high":
                success_factors.append("اتساق عالي في التسجيل")
            
            if not success_factors:
                success_factors.append("يحتاج تحسين في جميع المجالات")
            
            return success_factors
            
        except Exception:
            return ["خطأ في تحليل عوامل النجاح"]

    @staticmethod
    def _explain_load_recommendation(recommended_load: int, features: Dict) -> str:
        """شرح توصية العبء الدراسي"""
        try:
            current_gpa = features.get("current_gpa", 0)
            stress_level = features.get("stress_level", "متوسط")
            
            explanation = f"التوصية بـ {recommended_load} ساعة معتمدة بناءً على: "
            
            reasons = []
            if current_gpa >= 3.5:
                reasons.append("المعدل التراكمي الممتاز")
            elif current_gpa >= 3.0:
                reasons.append("المعدل التراكمي الجيد")
            else:
                reasons.append("الحاجة لتحسين المعدل التراكمي")
            
            if stress_level == "منخفض":
                reasons.append("مستوى ضغط منخفض")
            elif stress_level == "عالي":
                reasons.append("مستوى ضغط عالي")
            
            return explanation + "، ".join(reasons)
            
        except Exception:
            return f"توصية بـ {recommended_load} ساعة معتمدة"

    @staticmethod
    def _generate_load_alternatives(recommended_load: int) -> List[Dict]:
        """توليد بدائل العبء الدراسي"""
        alternatives = []
        
        try:
            # البديل المحافظ
            conservative_load = max(12, recommended_load - 3)
            alternatives.append({
                "load": conservative_load,
                "type": "محافظ",
                "description": "عبء دراسي أقل للتركيز على الجودة",
                "pros": ["تركيز أكبر", "ضغط أقل", "فرصة أفضل للتفوق"],
                "cons": ["تخرج أبطأ", "ساعات أقل"]
            })
            
            # البديل المتوازن (التوصية الأساسية)
            alternatives.append({
                "load": recommended_load,
                "type": "متوازن",
                "description": "العبء الدراسي الموصى به",
                "pros": ["توازن جيد", "تقدم مناسب", "إدارة جيدة للوقت"],
                "cons": ["قد يحتاج تنظيم دقيق"]
            })
            
            # البديل الطموح
            ambitious_load = min(21, recommended_load + 3)
            alternatives.append({
                "load": ambitious_load,
                "type": "طموح",
                "description": "عبء دراسي أكبر للتخرج المبكر",
                "pros": ["تخرج أسرع", "تحدي أكبر", "استغلال أفضل للوقت"],
                "cons": ["ضغط أكبر", "قد يؤثر على الجودة", "وقت أقل للأنشطة"]
            })
            
            return alternatives
            
        except Exception:
            return [{"load": recommended_load, "type": "افتراضي", "description": "العبء الموصى به"}]

    @staticmethod
    def _detect_performance_patterns(enrollments: List) -> Dict:
        """اكتشاف أنماط الأداء"""
        try:
            if not enrollments:
                return {"pattern": "no_data", "details": {}}
            
            # تحليل الأداء حسب نوع المادة
            subject_performance = {}
            time_performance = {}
            
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    # تحليل حسب نوع المادة (إذا توفر)
                    if hasattr(enrollment, 'course') and enrollment.course:
                        subject_type = getattr(enrollment.course, 'Type', 'عام')
                        if subject_type not in subject_performance:
                            subject_performance[subject_type] = []
                        subject_performance[subject_type].append(percentage)
                    
                    # تحليل حسب الوقت
                    semester = enrollment.Semester
                    if semester not in time_performance:
                        time_performance[semester] = []
                    time_performance[semester].append(percentage)
            
            # تحديد النمط
            patterns = []
            
            # نمط التحسن مع الوقت
            if len(time_performance) >= 3:
                semesters = sorted(time_performance.keys())
                early_avg = statistics.mean(time_performance[semesters[0]])
                recent_avg = statistics.mean(time_performance[semesters[-1]])
                
                if recent_avg > early_avg + 10:
                    patterns.append("متحسن مع الوقت")
                elif recent_avg < early_avg - 10:
                    patterns.append("متراجع مع الوقت")
                else:
                    patterns.append("أداء مستقر")
            
            # نمط التخصص
            if subject_performance:
                best_subject = max(subject_performance.keys(), 
                                 key=lambda k: statistics.mean(subject_performance[k]))
                worst_subject = min(subject_performance.keys(), 
                                  key=lambda k: statistics.mean(subject_performance[k]))
                
                if best_subject != worst_subject:
                    patterns.append(f"أداء أفضل في {best_subject}")
                    patterns.append(f"أداء أضعف في {worst_subject}")
            
            return {
                "pattern": patterns[0] if patterns else "أداء عادي",
                "all_patterns": patterns,
                "details": {
                    "subject_performance": {k: round(statistics.mean(v), 2) 
                                         for k, v in subject_performance.items()},
                    "time_performance": {k: round(statistics.mean(v), 2) 
                                       for k, v in time_performance.items()}
                }
            }
            
        except Exception as e:
            return {"pattern": "error", "details": {}, "error": str(e)}

    @staticmethod
    def _analyze_study_preferences(enrollments: List) -> Dict:
        """تحليل تفضيلات الدراسة"""
        try:
            if not enrollments:
                return {"preferences": "no_data", "analysis": {}}
            
            # تحليل الأداء حسب وقت المادة (إذا توفر)
            time_preferences = {"morning": [], "afternoon": [], "evening": []}
            difficulty_preferences = {"easy": [], "medium": [], "hard": []}
            
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    # تحليل حسب صعوبة المادة
                    if hasattr(enrollment, 'course') and enrollment.course:
                        credits = enrollment.course.Credits
                        if credits <= 2:
                            difficulty_preferences["easy"].append(percentage)
                        elif credits <= 3:
                            difficulty_preferences["medium"].append(percentage)
                        else:
                            difficulty_preferences["hard"].append(percentage)
            
            # تحديد التفضيلات
            preferences = []
            
            # تفضيل الصعوبة
            difficulty_avg = {}
            for level, grades in difficulty_preferences.items():
                if grades:
                    difficulty_avg[level] = statistics.mean(grades)
            
            if difficulty_avg:
                best_difficulty = max(difficulty_avg.keys(), 
                                    key=lambda k: difficulty_avg[k])
                preferences.append(f"يفضل المواد {best_difficulty}")
            
            return {
                "preferences": preferences,
                "analysis": {
                    "difficulty_performance": {k: round(v, 2) 
                                             for k, v in difficulty_avg.items()},
                    "recommendations": [
                        f"التركيز على المواد {best_difficulty}" if difficulty_avg else "تنويع المواد"
                    ]
                }
            }
            
        except Exception as e:
            return {"preferences": "error", "analysis": {}, "error": str(e)}

    @staticmethod
    def _detect_learning_style(enrollments: List) -> str:
        """اكتشاف نمط التعلم"""
        try:
            if not enrollments:
                return "غير محدد"
            
            # تحليل الأداء في أنواع مختلفة من المواد
            theoretical_grades = []
            practical_grades = []
            
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None):
                    
                    # حساب الدرجة الإجمالية من 150
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    # تصنيف المواد (هذا مثال، يمكن تحسينه)
                    if hasattr(enrollment, 'course') and enrollment.course:
                        course_name = enrollment.course.Name.lower()
                        if any(word in course_name for word in ['lab', 'practical', 'workshop', 'معمل', 'عملي']):
                            practical_grades.append(percentage)
                        else:
                            theoretical_grades.append(percentage)
            
            # تحديد نمط التعلم
            if practical_grades and theoretical_grades:
                practical_avg = statistics.mean(practical_grades)
                theoretical_avg = statistics.mean(theoretical_grades)
                
                if practical_avg > theoretical_avg + 10:
                    return "عملي"
                elif theoretical_avg > practical_avg + 10:
                    return "نظري"
                else:
                    return "متوازن"
            elif practical_grades:
                return "عملي"
            elif theoretical_grades:
                return "نظري"
            else:
                return "غير محدد"
                
        except Exception:
            return "غير محدد"

    @staticmethod
    def _generate_behavioral_recommendations(learning_style: str, patterns: Dict, preferences: Dict) -> List[str]:
        """توليد توصيات سلوكية"""
        recommendations = []
        
        try:
            # توصيات حسب نمط التعلم
            if learning_style == "عملي":
                recommendations.extend([
                    "التركيز على التطبيق العملي",
                    "البحث عن فرص التدريب العملي",
                    "استخدام المختبرات والورش"
                ])
            elif learning_style == "نظري":
                recommendations.extend([
                    "التركيز على الفهم النظري العميق",
                    "قراءة المراجع الإضافية",
                    "المشاركة في النقاشات الأكاديمية"
                ])
            else:
                recommendations.extend([
                    "الموازنة بين النظري والعملي",
                    "تنويع طرق التعلم"
                ])
            
            # توصيات حسب الأنماط
            pattern = patterns.get("pattern", "")
            if "تحسن" in pattern:
                recommendations.append("الاستمرار في النهج الحالي")
            elif "تراجع" in pattern:
                recommendations.append("مراجعة استراتيجية الدراسة")
            
            # توصيات حسب التفضيلات
            prefs = preferences.get("preferences", [])
            for pref in prefs:
                if "easy" in pref:
                    recommendations.append("تدرج في صعوبة المواد")
                elif "hard" in pref:
                    recommendations.append("تحدي النفس بمواد أكثر صعوبة")
            
            return list(set(recommendations))  # إزالة التكرار
            
        except Exception:
            return ["مراجعة الخطة الدراسية مع المرشد الأكاديمي"]

    @staticmethod
    def _detect_early_warnings(features: Dict) -> List[str]:
        """اكتشاف الإنذارات المبكرة"""
        warnings = []
        
        try:
            # تحليل المعدل التراكمي
            current_gpa = features.get("current_gpa", 0)
            if current_gpa < 2.0:
                warnings.append("معدل تراكمي منخفض جداً - خطر الفصل")
            elif current_gpa < 2.5:
                warnings.append("معدل تراكمي منخفض - يحتاج تحسين فوري")
            
            # تحليل الاتجاه
            gpa_trend = features.get("gpa_trend", {})
            if gpa_trend.get("trend") == "declining":
                slope = gpa_trend.get("slope", 0)
                if slope < -0.2:
                    warnings.append("تراجع سريع في المعدل التراكمي")
                else:
                    warnings.append("تراجع في المعدل التراكمي")
            
            # تحليل الحضور
            attendance_rate = features.get("attendance_rate", 1.0)
            if attendance_rate < 0.7:
                warnings.append("معدل حضور منخفض جداً")
            elif attendance_rate < 0.8:
                warnings.append("معدل حضور منخفض")
            
            # تحليل الإنذارات الأكاديمية
            warnings_count = features.get("warnings_count", 0)
            if warnings_count >= 2:
                warnings.append("عدد كبير من الإنذارات الأكاديمية")
            
            return warnings
            
        except Exception:
            return ["خطأ في تحليل الإنذارات المبكرة"]

    @staticmethod
    def _calculate_learning_efficiency(features: Dict) -> float:
        """حساب كفاءة التعلم"""
        try:
            current_gpa = features.get("current_gpa", 0)
            completion_rate = features.get("completion_rate", 0)
            attendance_rate = features.get("attendance_rate", 0)
            
            # حساب كفاءة التعلم كمتوسط مرجح
            efficiency = (current_gpa * 0.4 + 
                         completion_rate * 4 * 0.3 + 
                         attendance_rate * 4 * 0.3)
            
            return min(4.0, max(0.0, efficiency))
            
        except Exception:
            return 0.0

    @staticmethod
    def _interpret_efficiency(efficiency: float) -> str:
        """تفسير كفاءة التعلم"""
        if efficiency >= 3.5:
            return "كفاءة تعلم ممتازة"
        elif efficiency >= 3.0:
            return "كفاءة تعلم جيدة جداً"
        elif efficiency >= 2.5:
            return "كفاءة تعلم جيدة"
        elif efficiency >= 2.0:
            return "كفاءة تعلم مقبولة"
        else:
            return "كفاءة تعلم ضعيفة - تحتاج تحسين"

    @staticmethod
    def _calculate_stress_level(features: Dict) -> str:
        """حساب مستوى الضغط"""
        try:
            stress_score = 0
            
            # عوامل الضغط
            current_gpa = features.get("current_gpa", 0)
            if current_gpa < 2.5:
                stress_score += 30
            elif current_gpa < 3.0:
                stress_score += 15
            
            warnings_count = features.get("warnings_count", 0)
            stress_score += warnings_count * 20
            
            attendance_rate = features.get("attendance_rate", 1.0)
            if attendance_rate < 0.8:
                stress_score += 25
            
            # تحديد مستوى الضغط
            if stress_score >= 60:
                return "عالي"
            elif stress_score >= 30:
                return "متوسط"
            else:
                return "منخفض"
                
        except Exception:
            return "medium"

    @staticmethod
    def _identify_stressors(features: Dict) -> List[str]:
        """تحديد مصادر الضغط"""
        stressors = []
        
        try:
            current_gpa = features.get("current_gpa", 0)
            if current_gpa < 2.5:
                stressors.append("المعدل التراكمي المنخفض")
            
            warnings_count = features.get("warnings_count", 0)
            if warnings_count > 0:
                stressors.append("الإنذارات الأكاديمية")
            
            attendance_rate = features.get("attendance_rate", 1.0)
            if attendance_rate < 0.8:
                stressors.append("ضعف الحضور")
            
            gpa_trend = features.get("gpa_trend", {})
            if gpa_trend.get("trend") == "declining":
                stressors.append("تراجع الأداء")
            
            if not stressors:
                stressors.append("لا توجد مصادر ضغط واضحة")
            
            return stressors
            
        except Exception:
            return ["خطأ في تحديد مصادر الضغط"]

    @staticmethod
    def _suggest_coping_strategies(stress_level: str) -> List[str]:
        """اقتراح استراتيجيات التأقلم"""
        strategies = []
        
        if stress_level == "high":
            strategies.extend([
                "طلب المساعدة من المرشد الأكاديمي فوراً",
                "تقليل العبء الدراسي إذا أمكن",
                "وضع خطة دراسية مكثفة",
                "البحث عن دعم نفسي إذا لزم الأمر",
                "تنظيم الوقت بشكل صارم"
            ])
        elif stress_level == "medium":
            strategies.extend([
                "مراجعة الخطة الدراسية",
                "تحسين تنظيم الوقت",
                "طلب المساعدة في المواد الصعبة",
                "ممارسة تقنيات الاسترخاء"
            ])
        else:
            strategies.extend([
                "الحفاظ على التوازن الحالي",
                "التطلع لتحديات جديدة",
                "مساعدة الزملاء المحتاجين"
            ])
        
        return strategies 
class AcademicPathService:
    """خدمة التخطيط الأكاديمي للمسارات"""
    
    def __init__(self):
        # خريطة التشعيبات والمسارات
        self.path_mapping = {
            # مسار العلوم الطبيعية
            '1030': {'path': 'العلوم الطبيعية', 'stage': 'السنة الأولى', 'level': 1},
            '1035': {'path': 'العلوم الطبيعية', 'stage': 'الرياضيات والفيزياء', 'level': 2},
            '1095': {'path': 'العلوم الطبيعية', 'stage': 'الكيمياء والفيزياء', 'level': 2},
            '1040': {'path': 'العلوم الطبيعية', 'stage': 'الرياضيات الخاصة', 'level': 3},
            '1045': {'path': 'العلوم الطبيعية', 'stage': 'الفيزياء الخاصة', 'level': 3},
            '1050': {'path': 'العلوم الطبيعية', 'stage': 'الرياضيات وعلوم الحاسب', 'level': 3},
            '1055': {'path': 'العلوم الطبيعية', 'stage': 'الكيمياء الخاصة', 'level': 3},
            
            # مسار العلوم البيولوجية
            '1085': {'path': 'العلوم البيولوجية', 'stage': 'العلوم البيولوجية والكيميائية', 'level': 1},
            '1060': {'path': 'العلوم البيولوجية', 'stage': 'علم الحيوان', 'level': 3},
            '1065': {'path': 'العلوم البيولوجية', 'stage': 'النبات والكيمياء', 'level': 3},
            '1070': {'path': 'العلوم البيولوجية', 'stage': 'علم الحيوان والكيمياء', 'level': 3},
            '1075': {'path': 'العلوم البيولوجية', 'stage': 'الكيمياء والكيمياء الحيوية', 'level': 3},
            
            # مسار العلوم الجيولوجية
            '1090': {'path': 'العلوم الجيولوجية', 'stage': 'العلوم الجيولوجية والكيميائية', 'level': 1},
            '1080': {'path': 'العلوم الجيولوجية', 'stage': 'الجيولوجيا والكيمياء', 'level': 3}
        }
        
        # خريطة الانتقالات المسموحة
        self.transition_map = {
            '1030': ['1035', '1095'],  # من العلوم الطبيعية السنة الأولى
            '1035': ['1040', '1045', '1035', '1050'],  # من الرياضيات والفيزياء
            '1095': ['1055', '1095'],  # من الكيمياء والفيزياء
            '1085': ['1060', '1065', '1070', '1075'],  # من العلوم البيولوجية
            '1090': ['1080']  # من العلوم الجيولوجية
        }
    
    def get_student_academic_path(self, student_id):
        """الحصول على المسار الأكاديمي الكامل للطالب"""
        student = Students.query.get(student_id)
        if not student:
            return None
        
        # تحديد المسار الأكاديمي
        current_path = self._determine_academic_path(student)
        
        # حساب التقدم
        progress = self._calculate_student_progress(student)
        
        # الخطة المستقبلية
        future_plan = self._generate_future_plan(student, current_path)
        
        # التوصيات
        recommendations = self._generate_recommendations(student)
        
        return {
            'student_info': self._get_student_basic_info(student),
            'current_path': current_path,
            'progress': progress,
            'future_plan': future_plan,
            'recommendations': recommendations
        }
    
    def _get_student_basic_info(self, student):
        """معلومات الطالب الأساسية"""
        return {
            'id': student.Id,
            'name': student.Name,
            'current_semester': student.Semester,
            'division_id': student.DivisionId,
            'division_name': student.division.Name,
            'credits_completed': student.CreditsCompleted,
            'student_level': student.StudentLevel,
            'status': student.status
        }
    
    def _determine_academic_path(self, student):
        """تحديد المسار الأكاديمي بناءً على التشعيب الحالي"""
        division_name = student.division.Name
        
        path_info = self.path_mapping.get(division_name, {
            'path': 'غير محدد',
            'stage': 'غير محدد',
            'level': 0
        })
        
        return {
            'path_name': f"مسار {path_info['path']}",
            'current_stage': path_info['stage'],
            'stage_level': path_info['level'],
            'division_code': division_name,
            'division_display_name': self._get_division_display_name(division_name)
        }
    
    def _calculate_student_progress(self, student):
        """حساب تقدم الطالب مع مراعاة أن GPA لكل ترم منفصل"""
        current_year = self._calculate_academic_year(student.Semester)
        
        # حساب المعدل التراكمي الصحيح
        cumulative_gpa = self._calculate_cumulative_gpa(student)
        
        # الحصول على المقررات المكتملة
        completed_courses = self._get_completed_courses(student.Id)
        
        # التشعيبات المتاحة للمرحلة القادمة
        next_divisions = self._get_next_available_divisions(student)
        
        # تحليل الأداء الأكاديمي
        academic_performance = self._analyze_academic_performance(student)
        
        return {
            'current_year': current_year,
            'current_semester': student.Semester,
            'completed_courses_count': len(completed_courses),
            'credits_completed': student.CreditsCompleted,
            'cumulative_gpa': cumulative_gpa,
            'academic_performance': academic_performance,
            'next_available_divisions': next_divisions,
            'transition_eligibility': self._check_transition_eligibility(student, cumulative_gpa)
        }
    
    def _calculate_academic_year(self, semester):
        """حساب السنة الأكاديمية من الفصل الدراسي"""
        return (semester + 1) // 2
    
    def _calculate_cumulative_gpa(self, student):
        """حساب المعدل التراكمي الصحيح - مجموع GPAs ÷ عدد الترمات"""
        # الطالب في الترم 7 = لديه GPAs لـ 6 ترمات فقط
        completed_semesters = student.Semester - 1
        
        gpas = [student.GPA1, student.GPA2, student.GPA3, student.GPA4,
                student.GPA5, student.GPA6, student.GPA7, student.GPA8]
        
        # أخذ GPAs للترمات المكتملة فقط
        valid_gpas = []
        for i in range(min(completed_semesters, len(gpas))):
            if gpas[i] is not None:
                valid_gpas.append(gpas[i])
        
        if not valid_gpas:
            return 0.0
        
        cumulative_gpa = sum(valid_gpas) / len(valid_gpas)
        
        return {
            'current_cumulative': round(cumulative_gpa, 2),
            'completed_semesters': len(valid_gpas),
            'semester_gpas': valid_gpas,
            'trend': self._calculate_gpa_trend(valid_gpas)
        }
    
    def _calculate_gpa_trend(self, gpas):
        """حساب اتجاه المعدل التراكمي"""
        if len(gpas) < 2:
            return 'غير كافي للتحليل'
        
        # مقارنة آخر ترمين مع الترمات السابقة
        recent_avg = sum(gpas[-2:]) / 2 if len(gpas) >= 2 else gpas[-1]
        earlier_avg = sum(gpas[:-2]) / len(gpas[:-2]) if len(gpas) > 2 else gpas[0]
        
        if recent_avg > earlier_avg + 0.2:
            return 'متحسن'
        elif recent_avg < earlier_avg - 0.2:
            return 'متراجع'
        else:
            return 'مستقر'
    
    def _get_completed_courses(self, student_id):
        """الحصول على المقررات المكتملة للطالب"""
        completed_enrollments = Enrollments.query.filter(
            and_(
                Enrollments.StudentId == student_id,
                Enrollments.IsCompleted == 'ناجح',
                Enrollments.Grade.isnot(None)
            )
        ).all()
        
        completed_courses = []
        for enrollment in completed_enrollments:
            completed_courses.append({
                'course_id': enrollment.CourseId,
                'course_name': enrollment.course.Name,
                'course_code': enrollment.course.Code,
                'credits': enrollment.course.Credits,
                'grade': float(enrollment.Grade) if enrollment.Grade else None,
                'semester': enrollment.Semester
            })
        
        return completed_courses
    
    def _get_next_available_divisions(self, student):
        """تحديد التشعيبات المتاحة للطالب في المرحلة القادمة"""
        current_division = student.division.Name
        current_year = self._calculate_academic_year(student.Semester)
        
        # التحقق من إمكانية الانتقال بناءً على السنة الأكاديمية
        available_division_codes = []
        
        if current_division in self.transition_map:
            if (current_division in ['1030'] and current_year >= 2) or \
               (current_division in ['1035', '1095', '1085', '1090'] and current_year >= 3):
                available_division_codes = self.transition_map[current_division]
        
        # الحصول على تفاصيل التشعيبات من قاعدة البيانات
        available_divisions = []
        for div_code in available_division_codes:
            division = Divisions.query.filter_by(Name=div_code).first()
            if division:
                available_divisions.append({
                    'id': division.Id,
                    'code': division.Name,
                    'name': self._get_division_display_name(division.Name),
                    'department_id': division.DepartmentId,
                    'department_name': division.department.Name if division.department else 'غير محدد'
                })
        
        return available_divisions
    
    def _get_division_display_name(self, division_code):
        """الحصول على الاسم المعروض للتشعيب"""
        display_names = {
            '1030': 'مجموعة العلوم الطبيعية',
            '1035': 'الرياضيات والفيزياء',
            '1095': 'الكيمياء والفيزياء',
            '1040': 'الرياضيات الخاصة',
            '1045': 'الفيزياء الخاصة',
            '1050': 'الرياضيات وعلوم الحاسب',
            '1055': 'الكيمياء الخاصة',
            '1085': 'العلوم البيولوجية والكيميائية',
            '1060': 'علم الحيوان',
            '1065': 'النبات والكيمياء',
            '1070': 'علم الحيوان والكيمياء',
            '1075': 'الكيمياء والكيمياء الحيوية',
            '1090': 'العلوم الجيولوجية والكيميائية',
            '1080': 'الجيولوجيا والكيمياء'
        }
        
        return display_names.get(division_code, division_code)
    
    def _analyze_academic_performance(self, student):
        """تحليل الأداء الأكاديمي للطالب"""
        cumulative_gpa_info = self._calculate_cumulative_gpa(student)
        current_gpa = cumulative_gpa_info['current_cumulative']
        
        # تحديد مستوى الأداء
        if current_gpa >= 3.5:
            performance_level = 'ممتاز'
        elif current_gpa >= 3.0:
            performance_level = 'جيد جداً'
        elif current_gpa >= 2.5:
            performance_level = 'جيد'
        elif current_gpa >= 2.0:
            performance_level = 'مقبول'
        else:
            performance_level = 'ضعيف'
        
        return {
            'current_cumulative_gpa': current_gpa,
            'gpa_trend': cumulative_gpa_info['trend'],
            'performance_level': performance_level,
            'completed_semesters': cumulative_gpa_info['completed_semesters'],
            'semester_gpas': cumulative_gpa_info['semester_gpas']
        }
    
    def _check_transition_eligibility(self, student, cumulative_gpa_info):
        """التحقق من أهلية الطالب للانتقال"""
        current_gpa = cumulative_gpa_info['current_cumulative']
        credits_completed = student.CreditsCompleted
        current_year = self._calculate_academic_year(student.Semester)
        
        eligibility = {
            'is_eligible': True,
            'requirements_met': [],
            'requirements_missing': [],
            'recommendations': []
        }
        
        # متطلبات الانتقال العامة
        min_gpa_required = 2.0
        min_credits_per_year = 30
        
        if current_gpa >= min_gpa_required:
            eligibility['requirements_met'].append(f'المعدل التراكمي ({current_gpa:.2f}) يلبي الحد الأدنى')
        else:
            eligibility['requirements_missing'].append(f'المعدل التراكمي ({current_gpa:.2f}) أقل من المطلوب ({min_gpa_required})')
            eligibility['is_eligible'] = False
        
        expected_credits = current_year * min_credits_per_year
        if credits_completed >= expected_credits:
            eligibility['requirements_met'].append(f'الساعات المكتملة ({credits_completed}) كافية')
        else:
            eligibility['requirements_missing'].append(f'نقص في الساعات المكتملة ({credits_completed}/{expected_credits})')
        
        # إضافة توصيات
        if not eligibility['is_eligible']:
            eligibility['recommendations'].append('ننصح بالتركيز على تحسين المعدل التراكمي قبل الانتقال')
        
        if current_gpa >= 3.0:
            eligibility['recommendations'].append('أداؤك الأكاديمي جيد، يمكنك اختيار التخصص المناسب لميولك')
        
        return eligibility
    
    def _generate_future_plan(self, student, current_path):
        """توليد الخطة المستقبلية للطالب"""
        current_year = self._calculate_academic_year(student.Semester)
        remaining_years = max(0, 4 - current_year)
        
        future_plan = {
            'remaining_years': remaining_years,
            'remaining_semesters': max(0, 8 - student.Semester + 1),
            'expected_graduation_year': datetime.now().year + remaining_years,
            'next_milestones': self._get_next_milestones(student, current_path),
            'graduation_requirements': self._get_graduation_requirements(),
            'recommended_timeline': self._generate_timeline(student, current_path)
        }
        
        return future_plan
    
    def _get_next_milestones(self, student, current_path):
        """الحصول على المعالم القادمة في المسار"""
        milestones = []
        current_year = self._calculate_academic_year(student.Semester)
        
        if current_path['stage_level'] == 1:  # السنة الأولى
            milestones.append({
                'milestone': 'اختيار التخصص الفرعي',
                'expected_semester': 4,
                'description': 'اختيار التشعيب للسنة الثانية'
            })
        elif current_path['stage_level'] == 2:  # السنة الثانية
            milestones.append({
                'milestone': 'اختيار التخصص النهائي',
                'expected_semester': 6,
                'description': 'اختيار التشعيب للسنة الثالثة والرابعة'
            })
        elif current_path['stage_level'] == 3:  # السنة الثالثة والرابعة
            milestones.append({
                'milestone': 'مشروع التخرج',
                'expected_semester': 8,
                'description': 'إكمال مشروع التخرج والتخرج'
            })
        
        return milestones
    
    def _get_graduation_requirements(self):
        """متطلبات التخرج العامة"""
        return {
            'total_credits': 144,
            'minimum_gpa': 2.0,
            'mandatory_courses': 'إكمال جميع المقررات الإجبارية',
            'elective_courses': 'إكمال العدد المطلوب من المقررات الاختيارية',
            'final_project': 'مشروع التخرج',
            'minimum_years': 4
        }
    
    def _generate_timeline(self, student, current_path):
        """توليد الجدول الزمني للخطة"""
        current_year = self._calculate_academic_year(student.Semester)
        timeline = []
        
        for year in range(current_year, 5):
            year_plan = {
                'academic_year': year,
                'semesters': [year * 2 - 1, year * 2],
                'focus_areas': self._get_year_focus_areas(year, current_path),
                'key_decisions': self._get_year_key_decisions(year, current_path),
                'expected_credits': 36
            }
            timeline.append(year_plan)
        
        return timeline
    
    def _get_year_focus_areas(self, year, current_path):
        """مجالات التركيز لكل سنة"""
        if current_path['path_name'] == 'مسار العلوم الطبيعية':
            focus_map = {
                1: ['المقررات الأساسية', 'الرياضيات العامة', 'الفيزياء العامة'],
                2: ['التخصص الفرعي', 'المقررات المتقدمة'],
                3: ['التخصص النهائي', 'المقررات التخصصية'],
                4: ['مشروع التخرج', 'المقررات المتقدمة']
            }
        elif current_path['path_name'] == 'مسار العلوم البيولوجية':
            focus_map = {
                1: ['العلوم البيولوجية الأساسية', 'الكيمياء العامة'],
                2: ['العلوم البيولوجية المتقدمة', 'الكيمياء الحيوية'],
                3: ['التخصص النهائي', 'البحث العلمي'],
                4: ['مشروع التخرج', 'التطبيقات العملية']
            }
        else:  # العلوم الجيولوجية
            focus_map = {
                1: ['الجيولوجيا الأساسية', 'الكيمياء العامة'],
                2: ['الجيولوجيا المتقدمة', 'التدريب الميداني'],
                3: ['التخصص النهائي', 'الجيولوجيا التطبيقية'],
                4: ['مشروع التخرج', 'التدريب المهني']
            }
        
        return focus_map.get(year, ['مقررات عامة'])
    
    def _get_year_key_decisions(self, year, current_path):
        """القرارات المهمة لكل سنة"""
        if current_path['path_name'] == 'مسار العلوم الطبيعية':
            decisions_map = {
                2: ['اختيار بين الرياضيات والفيزياء أو الكيمياء والفيزياء'],
                3: ['اختيار التخصص النهائي من التشعيبات المتاحة'],
                4: ['اختيار موضوع مشروع التخرج']
            }
        elif current_path['path_name'] == 'مسار العلوم البيولوجية':
            decisions_map = {
                3: ['اختيار التخصص النهائي في العلوم البيولوجية'],
                4: ['اختيار مجال البحث لمشروع التخرج']
            }
        else:  # العلوم الجيولوجية
            decisions_map = {
                3: ['التخصص في الجيولوجيا والكيمياء'],
                4: ['اختيار مجال التطبيق في مشروع التخرج']
            }
        
        return decisions_map.get(year, [])
    
    def _generate_recommendations(self, student):
        """توصيات للمسار الأكاديمي"""
        recommendations = []
        
        # تحليل الأداء الأكاديمي
        performance = self._analyze_academic_performance(student)
        
        # توصيات بناءً على الأداء
        if performance['performance_level'] == 'ممتاز':
            recommendations.append({
                'type': 'success',
                'title': 'أداء متميز',
                'message': 'أداؤك الأكاديمي ممتاز، يمكنك اختيار أي تخصص تفضله',
                'priority': 'high'
            })
        elif performance['performance_level'] == 'ضعيف':
            recommendations.append({
                'type': 'warning',
                'title': 'تحسين الأداء مطلوب',
                'message': 'ننصح بالتركيز على تحسين المعدل التراكمي قبل اختيار التخصص',
                'priority': 'high'
            })
        
        # توصيات بناءً على التشعيبات المتاحة
        next_divisions = self._get_next_available_divisions(student)
        if next_divisions:
            recommendations.append({
                'type': 'info',
                'title': 'خيارات التخصص',
                'message': f'لديك {len(next_divisions)} خيارات متاحة للتخصص في المرحلة القادمة',
                'priority': 'medium'
            })
        
        # توصيات بناءً على الساعات المكتملة
        if student.CreditsCompleted < 30:
            recommendations.append({
                'type': 'warning',
                'title': 'الساعات المكتملة',
                'message': 'ننصح بزيادة عدد الساعات المسجلة لتجنب التأخير في التخرج',
                'priority': 'medium'
            })
        
        return recommendations


class DivisionRecommendationService:
    """خدمة توصيات التشعيبات"""
    
    def __init__(self):
        self.path_service = AcademicPathService()
    
    def get_division_recommendations(self, student_id):
        """توصيات التشعيب المفصلة للطالب"""
        student = Students.query.get(student_id)
        if not student:
            return None
        
        # الحصول على التشعيبات المتاحة
        available_divisions = self.path_service._get_next_available_divisions(student)
        
        # تحليل نقاط القوة الأكاديمية
        academic_strengths = self._analyze_academic_strengths(student)
        
        # توليد توصيات مفصلة
        detailed_recommendations = []
        for division in available_divisions:
            recommendation = self._generate_division_recommendation(student, division, academic_strengths)
            detailed_recommendations.append(recommendation)
        
        # ترتيب التوصيات حسب درجة الملاءمة
        detailed_recommendations.sort(key=lambda x: x['suitability_score'], reverse=True)
        
        return {
            'student_id': student_id,
            'student_name': student.Name,
            'current_division': {
                'id': student.DivisionId,
                'name': student.division.Name,
                'display_name': self.path_service._get_division_display_name(student.division.Name)
            },
            'academic_strengths': academic_strengths,
            'recommendations': detailed_recommendations,
            'generated_at': datetime.now().isoformat()
        }
    
    def _analyze_academic_strengths(self, student):
        """تحليل نقاط القوة الأكاديمية بناءً على الدرجات في المقررات"""
        enrollments = Enrollments.query.filter(
            and_(
                Enrollments.StudentId == student.Id,
                Enrollments.Grade.isnot(None)
            )
        ).all()
        
        subject_performance = {}
        
        for enrollment in enrollments:
            course = enrollment.course
            subject_type = self._categorize_course(course.Name)
            
            if subject_type not in subject_performance:
                subject_performance[subject_type] = []
            
            subject_performance[subject_type].append(float(enrollment.Grade))
        
        # حساب المتوسطات ونقاط القوة
        strengths = {}
        for subject_type, grades in subject_performance.items():
            average = sum(grades) / len(grades)
            strengths[subject_type] = {
                'average_grade': round(average, 2),
                'courses_count': len(grades),
                'strength_level': self._determine_strength_level(average),
                'grades': grades
            }
        
        return strengths
    
    def _categorize_course(self, course_name):
        """تصنيف المقرر حسب المجال العلمي"""
        course_name_lower = course_name.lower()
        
        # قاموس الكلمات المفتاحية لكل مجال
        categories = {
            'mathematics': ['رياض', 'math', 'حساب', 'إحصاء', 'جبر', 'هندسة', 'تفاضل', 'تكامل'],
            'physics': ['فيزياء', 'physics', 'فيزيقا'],
            'chemistry': ['كيمياء', 'chemistry', 'كيميائي'],
            'biology': ['أحياء', 'biology', 'حيوان', 'نبات', 'وراثة', 'خلية'],
            'geology': ['جيولوجيا', 'geology', 'أرض', 'معادن', 'صخور'],
            'computer_science': ['حاسب', 'computer', 'برمجة', 'خوارزم', 'بيانات']
        }
        
        for category, keywords in categories.items():
            if any(keyword in course_name_lower for keyword in keywords):
                return category
        
        return 'general'
    
    def _determine_strength_level(self, average_grade):
        """تحديد مستوى القوة بناءً على المتوسط"""
        if average_grade >= 3.5:
            return 'ممتاز'
        elif average_grade >= 3.0:
            return 'جيد جداً'
        elif average_grade >= 2.5:
            return 'جيد'
        elif average_grade >= 2.0:
            return 'مقبول'
        else:
            return 'ضعيف'
    
    def _generate_division_recommendation(self, student, division, academic_strengths):
        """توليد توصية مفصلة لتشعيب معين"""
        suitability_score = self._calculate_suitability_score(student, division, academic_strengths)
        
        recommendation = {
            'division_id': division['id'],
            'division_code': division['code'],
            'division_name': division['name'],
            'department_name': division['department_name'],
            'suitability_score': suitability_score,
            'recommendation_level': self._get_recommendation_level(suitability_score),
            'strengths_alignment': self._analyze_strengths_alignment(division, academic_strengths),
            'reasons': self._get_recommendation_reasons(student, division, academic_strengths),
            'requirements': self._get_division_requirements(division['code']),
            'career_prospects': self._get_career_prospects(division['code']),
            'courses_info': self._get_division_courses_info(division['id'])
        }
        
        return recommendation
    
    def _calculate_suitability_score(self, student, division, academic_strengths):
        """حساب درجة ملاءمة التشعيب للطالب"""
        base_score = 50
        
        # عامل المعدل التراكمي
        cumulative_gpa_info = self.path_service._calculate_cumulative_gpa(student)
        current_gpa = cumulative_gpa_info['current_cumulative']
        
        if current_gpa >= 3.5:
            base_score += 20
        elif current_gpa >= 3.0:
            base_score += 15
        elif current_gpa >= 2.5:
            base_score += 10
        elif current_gpa < 2.0:
            base_score -= 10
        
        # عامل نقاط القوة الأكاديمية
        division_code = division['code']
        
        # تحليل بناءً على نوع التشعيب
        if division_code in ['1040', '1050']:  # تشعيبات الرياضيات
            if 'mathematics' in academic_strengths:
                math_level = academic_strengths['mathematics']['strength_level']
                if math_level == 'ممتاز':
                    base_score += 25
                elif math_level == 'جيد جداً':
                    base_score += 20
                elif math_level == 'جيد':
                    base_score += 15
        
        elif division_code == '1045':  # الفيزياء الخاصة
            physics_bonus = 0
            math_bonus = 0
            
            if 'physics' in academic_strengths:
                physics_level = academic_strengths['physics']['strength_level']
                if physics_level == 'ممتاز':
                    physics_bonus = 20
                elif physics_level == 'جيد جداً':
                    physics_bonus = 15
            
            if 'mathematics' in academic_strengths:
                math_level = academic_strengths['mathematics']['strength_level']
                if math_level in ['ممتاز', 'جيد جداً']:
                    math_bonus = 10
            
            base_score += physics_bonus + math_bonus
        
        elif division_code in ['1055', '1095']:  # تشعيبات الكيمياء
            if 'chemistry' in academic_strengths:
                chem_level = academic_strengths['chemistry']['strength_level']
                if chem_level == 'ممتاز':
                    base_score += 25
                elif chem_level == 'جيد جداً':
                    base_score += 20
        
        elif division_code in ['1060', '1065', '1070', '1075']:  # تشعيبات البيولوجيا
            if 'biology' in academic_strengths:
                bio_level = academic_strengths['biology']['strength_level']
                if bio_level == 'ممتاز':
                    base_score += 25
                elif bio_level == 'جيد جداً':
                    base_score += 20
        
        elif division_code == '1080':  # الجيولوجيا
            if 'geology' in academic_strengths:
                geo_level = academic_strengths['geology']['strength_level']
                if geo_level == 'ممتاز':
                    base_score += 25
                elif geo_level == 'جيد جداً':
                    base_score += 20
        
        return min(100, max(0, base_score))
    
    def _get_recommendation_level(self, score):
        """تحديد مستوى التوصية بناءً على النقاط"""
        if score >= 80:
            return 'موصى به بشدة'
        elif score >= 65:
            return 'موصى به'
        elif score >= 50:
            return 'مناسب'
        else:
            return 'غير موصى به'
    
    def _analyze_strengths_alignment(self, division, academic_strengths):
        """تحليل مدى توافق نقاط القوة مع التشعيب"""
        division_code = division['code']
        alignment = []
        
        # تحديد المجالات المطلوبة لكل تشعيب
        required_strengths = {
            '1040': ['mathematics'],  # الرياضيات الخاصة
            '1045': ['physics', 'mathematics'],  # الفيزياء الخاصة
            '1050': ['mathematics', 'computer_science'],  # الرياضيات وعلوم الحاسب
            '1055': ['chemistry'],  # الكيمياء الخاصة
            '1095': ['chemistry', 'physics'],  # الكيمياء والفيزياء
            '1060': ['biology'],  # علم الحيوان
            '1065': ['biology', 'chemistry'],  # النبات والكيمياء
            '1070': ['biology', 'chemistry'],  # علم الحيوان والكيمياء
            '1075': ['chemistry', 'biology'],  # الكيمياء والكيمياء الحيوية
            '1080': ['geology', 'chemistry']  # الجيولوجيا والكيمياء
        }
        
        required = required_strengths.get(division_code, [])
        
        for strength_area in required:
            if strength_area in academic_strengths:
                strength_info = academic_strengths[strength_area]
                alignment.append({
                    'area': strength_area,
                    'level': strength_info['strength_level'],
                    'average_grade': strength_info['average_grade'],
                    'is_strong': strength_info['strength_level'] in ['ممتاز', 'جيد جداً']
                })
            else:
                alignment.append({
                    'area': strength_area,
                    'level': 'غير متوفر',
                    'average_grade': 0,
                    'is_strong': False
                })
        
        return alignment
    
    def _get_recommendation_reasons(self, student, division, academic_strengths):
        """أسباب التوصية"""
        reasons = []
        
        # تحليل نقاط القوة
        alignment = self._analyze_strengths_alignment(division, academic_strengths)
        
        for align in alignment:
            if align['is_strong']:
                reasons.append(f"أداء {align['level']} في مجال {self._translate_subject(align['area'])}")
        
        # تحليل المعدل التراكمي
        cumulative_gpa_info = self.path_service._calculate_cumulative_gpa(student)
        current_gpa = cumulative_gpa_info['current_cumulative']
        if current_gpa >= 3.0:
            reasons.append(f"معدل تراكمي جيد ({current_gpa:.2f})")
        
        # أسباب خاصة بكل تشعيب
        division_specific_reasons = self._get_division_specific_reasons(division['code'], student)
        reasons.extend(division_specific_reasons)
        
        return reasons
    
    def _translate_subject(self, subject):
        """ترجمة أسماء المواد"""
        translations = {
            'mathematics': 'الرياضيات',
            'physics': 'الفيزياء',
            'chemistry': 'الكيمياء',
            'biology': 'الأحياء',
            'geology': 'الجيولوجيا',
            'computer_science': 'علوم الحاسب'
        }
        return translations.get(subject, subject)
    
    def _get_division_specific_reasons(self, division_code, student):
        """أسباب خاصة بكل تشعيب"""
        reasons = []
        
        if division_code == '1050':  # الرياضيات وعلوم الحاسب
            reasons.append("مجال متنامي مع فرص عمل ممتازة في التكنولوجيا")
        elif division_code == '1045':  # الفيزياء الخاصة
            reasons.append("أساس قوي للدراسات العليا والبحث العلمي")
        elif division_code in ['1060', '1065', '1070', '1075']:  # البيولوجيا
            reasons.append("مجال حيوي مع تطبيقات في الطب والبيئة")
        
        return reasons
    
    def _get_division_requirements(self, division_code):
        """متطلبات كل تشعيب"""
        requirements = {
            '1040': ['تفوق في الرياضيات', 'معدل تراكمي لا يقل عن 2.5'],
            '1045': ['تفوق في الفيزياء والرياضيات', 'مهارات تحليلية قوية'],
            '1050': ['تفوق في الرياضيات', 'مهارات أساسية في الحاسوب'],
            '1055': ['تفوق في الكيمياء', 'مهارات معملية جيدة'],
            '1095': ['أداء جيد في الكيمياء والفيزياء'],
            '1060': ['تفوق في علم الحيوان', 'مهارات بحثية'],
            '1065': ['أداء جيد في النبات والكيمياء'],
            '1070': ['تفوق في علم الحيوان والكيمياء'],
            '1075': ['تفوق في الكيمياء والكيمياء الحيوية'],
            '1080': ['أداء جيد في الجيولوجيا والكيمياء', 'استعداد للعمل الميداني']
        }
        
        return requirements.get(division_code, ['متطلبات عامة'])
    
    def _get_career_prospects(self, division_code):
        """الفرص المهنية لكل تشعيب"""
        prospects = {
            '1040': ['التعليم الجامعي', 'البحث العلمي', 'التحليل الإحصائي', 'الاستشارات المالية'],
            '1045': ['البحث العلمي', 'الصناعة', 'التكنولوجيا', 'الطاقة'],
            '1050': ['تطوير البرمجيات', 'تحليل البيانات', 'الذكاء الاصطناعي', 'الأمن السيبراني'],
            '1055': ['الصناعات الكيميائية', 'البحث والتطوير', 'مراقبة الجودة', 'البيئة'],
            '1095': ['الصناعة', 'البحث العلمي', 'التحليل الكيميائي'],
            '1060': ['البحث البيولوجي', 'المحميات الطبيعية', 'التعليم'],
            '1065': ['الزراعة', 'البيئة', 'البحث النباتي'],
            '1070': ['البحث البيولوجي', 'المختبرات الطبية', 'البيئة'],
            '1075': ['الصناعات الدوائية', 'البحث الطبي', 'التحليل الحيوي'],
            '1080': ['شركات البترول', 'المناجم', 'الاستشارات الجيولوجية', 'البحث البيئي']
        }
        
        return prospects.get(division_code, ['فرص متنوعة'])
    
    def _get_division_courses_info(self, division_id):
        """معلومات المقررات المتاحة في التشعيب"""
        courses = db.session.query(Courses).join(CourseDivisions).filter(
            CourseDivisions.DivisionId == division_id
        ).all()
        
        courses_info = {
            'total_courses': len(courses),
            'mandatory_courses': len([c for c in courses if any(cd.IsMandatory for cd in c.course_divisions if cd.DivisionId == division_id)]),
            'total_credits': sum(c.Credits for c in courses),
            'sample_courses': [
                {
                    'name': course.Name,
                    'code': course.Code,
                    'credits': course.Credits,
                    'semester': course.Semester
                } for course in courses[:5]  # أول 5 مقررات كعينة
            ]
        }
        
        return courses_info


class VerySmartAcademicPathPlanningService:
    """خدمة التخطيط الأكاديمي الذكي المتقدم - تدمج جميع الخدمات الموجودة"""
    
    def __init__(self):
        # استيراد الخدمات الموجودة لتجنب التكرار
        try:
            from services import SmartCourseRecommendationService
            from services import AcademicStatusAnalysisService
            from services import AcademicWarningService
            from services import GraduationEligibilityService
            
            # الخدمات الموجودة
            self.path_service = AcademicPathService()
            self.recommendation_service = DivisionRecommendationService()
            self.course_service = SmartCourseRecommendationService()
            self.status_service = AcademicStatusAnalysisService()
            self.warning_service = AcademicWarningService()
            self.graduation_service = GraduationEligibilityService()
        except ImportError:
            # في حالة عدم توفر بعض الخدمات، استخدم الخدمات المتاحة فقط
            self.path_service = AcademicPathService()
            self.recommendation_service = DivisionRecommendationService()
            self.course_service = None
            self.status_service = None
            self.warning_service = None
            self.graduation_service = None
        
        # أوزان الذكاء الاصطناعي للتخطيط المتقدم
        self.ai_weights = {
            'academic_performance': 0.25,
            'learning_patterns': 0.20,
            'career_alignment': 0.15,
            'risk_mitigation': 0.15,
            'graduation_optimization': 0.15,
            'personal_preferences': 0.10
        }
    
    def get_very_smart_academic_plan(self, student_id):
        """الحصول على الخطة الأكاديمية الذكية المتقدمة"""
        try:
            # جمع البيانات من جميع الخدمات الموجودة
            comprehensive_data = self._gather_comprehensive_data(student_id)
            
            if 'error' in comprehensive_data:
                return comprehensive_data
            
            # تطبيق الذكاء الاصطناعي للتحليل المتقدم
            ai_analysis = self._apply_ai_analysis(comprehensive_data)
            
            # توليد الخطة الذكية المخصصة
            smart_plan = self._generate_smart_plan(comprehensive_data, ai_analysis)
            
            # التنبؤ بالمسارات المستقبلية
            future_predictions = self._predict_future_paths(comprehensive_data, ai_analysis)
            
            # توصيات التحسين المستمر
            optimization_recommendations = self._generate_optimization_recommendations(
                comprehensive_data, ai_analysis, smart_plan
            )
            
            return {
                'student_id': student_id,
                'comprehensive_analysis': comprehensive_data,
                'ai_insights': ai_analysis,
                'smart_academic_plan': smart_plan,
                'future_predictions': future_predictions,
                'optimization_recommendations': optimization_recommendations,
                'generated_at': datetime.now().isoformat(),
                'plan_version': '2.0_ai_enhanced'
            }
            
        except Exception as e:
            return {
                'error': f'خطأ في توليد الخطة الذكية: {str(e)}',
                'student_id': student_id
            }
    
    def _gather_comprehensive_data(self, student_id):
        """جمع البيانات الشاملة من جميع الخدمات"""
        try:
            # البيانات الأساسية للمسار الأكاديمي
            path_data = self.path_service.get_student_academic_path(student_id)
            if not path_data:
                return {'error': 'الطالب غير موجود'}
            
            # جمع البيانات من الخدمات المتاحة
            comprehensive_data = {
                'basic_path': path_data,
                'data_quality': self._assess_data_quality(path_data)
            }
            
            # التحليل الأكاديمي الشامل
            if self.status_service:
                try:
                    status_analysis = self.status_service.get_comprehensive_analysis(student_id)
                    comprehensive_data['comprehensive_status'] = status_analysis
                except:
                    comprehensive_data['comprehensive_status'] = None
            
            # توصيات المقررات الذكية
            if self.course_service:
                try:
                    course_recommendations = self.course_service.get_smart_recommendations(student_id)
                    comprehensive_data['course_recommendations'] = course_recommendations
                except:
                    comprehensive_data['course_recommendations'] = None
            
            # توصيات التشعيبات
            division_recommendations = self.recommendation_service.get_division_recommendations(student_id)
            comprehensive_data['division_recommendations'] = division_recommendations
            
            # أهلية التخرج
            if self.graduation_service:
                try:
                    graduation_eligibility = self.graduation_service.get_graduation_eligibility(student_id)
                    comprehensive_data['graduation_status'] = graduation_eligibility
                except:
                    comprehensive_data['graduation_status'] = None
            
            # الإنذارات الأكاديمية
            if self.warning_service:
                try:
                    academic_warnings = self.warning_service.get_student_warnings(student_id)
                    comprehensive_data['academic_warnings'] = academic_warnings
                except:
                    comprehensive_data['academic_warnings'] = []
            
            return comprehensive_data
            
        except Exception as e:
            return {'error': f'خطأ في جمع البيانات: {str(e)}'}
    
    def _assess_data_quality(self, path_data):
        """تقييم جودة البيانات المتاحة"""
        quality_score = 100
        issues = []
        
        # فحص اكتمال البيانات الأساسية
        if not path_data.get('student_info', {}).get('current_semester'):
            quality_score -= 20
            issues.append('بيانات الفصل الدراسي ناقصة')
        
        if not path_data.get('progress', {}).get('cumulative_gpa'):
            quality_score -= 15
            issues.append('بيانات المعدل التراكمي ناقصة')
        
        # فحص بيانات المقررات
        completed_courses = path_data.get('progress', {}).get('completed_courses_count', 0)
        if completed_courses == 0:
            quality_score -= 25
            issues.append('لا توجد مقررات مكتملة مسجلة')
        
        return {
            'score': max(0, quality_score),
            'level': 'ممتاز' if quality_score >= 90 else 'جيد' if quality_score >= 70 else 'مقبول' if quality_score >= 50 else 'ضعيف',
            'issues': issues,
            'recommendations': self._get_data_improvement_recommendations(issues)
        }
    
    def _get_data_improvement_recommendations(self, issues):
        """توصيات لتحسين جودة البيانات"""
        recommendations = []
        
        if 'بيانات الفصل الدراسي ناقصة' in issues:
            recommendations.append('تحديث بيانات الفصل الدراسي الحالي')
        
        if 'بيانات المعدل التراكمي ناقصة' in issues:
            recommendations.append('إدخال درجات الفصول الدراسية المكتملة')
        
        if 'لا توجد مقررات مكتملة مسجلة' in issues:
            recommendations.append('تسجيل المقررات المكتملة والدرجات المحققة')
        
        return recommendations
    
    def _apply_ai_analysis(self, comprehensive_data):
        """تطبيق تحليل الذكاء الاصطناعي المتقدم"""
        try:
            # تحليل أنماط التعلم
            learning_patterns = self._analyze_learning_patterns(comprehensive_data)
            
            # تحليل المخاطر الأكاديمية
            risk_analysis = self._analyze_academic_risks(comprehensive_data)
            
            # تحليل التوافق المهني
            career_alignment = self._analyze_career_alignment(comprehensive_data)
            
            # تحليل الكفاءة الأكاديمية
            efficiency_analysis = self._analyze_academic_efficiency(comprehensive_data)
            
            # التنبؤ بالأداء المستقبلي
            performance_prediction = self._predict_future_performance(comprehensive_data)
            
            # تحليل الفرص والتحديات
            opportunities_threats = self._analyze_opportunities_threats(comprehensive_data)
            
            return {
                'learning_patterns': learning_patterns,
                'risk_analysis': risk_analysis,
                'career_alignment': career_alignment,
                'efficiency_analysis': efficiency_analysis,
                'performance_prediction': performance_prediction,
                'opportunities_threats': opportunities_threats,
                'overall_ai_score': self._calculate_overall_ai_score(
                    learning_patterns, risk_analysis, career_alignment, 
                    efficiency_analysis, performance_prediction
                )
            }
            
        except Exception as e:
            return {'error': f'خطأ في التحليل الذكي: {str(e)}'}
    
    def _analyze_learning_patterns(self, data):
        """تحليل أنماط التعلم والأداء"""
        try:
            status_data = data.get('comprehensive_status', {})
            path_data = data.get('basic_path', {})
            
            # تحليل اتجاه المعدل التراكمي
            gpa_analysis = path_data.get('progress', {}).get('cumulative_gpa', {})
            gpa_trend = gpa_analysis.get('trend', 'مستقر')
            
            # تحليل الأداء الأكاديمي
            academic_performance = path_data.get('progress', {}).get('academic_performance', {})
            
            # تحديد نمط التعلم المفضل
            preferred_learning_style = self._determine_learning_style(academic_performance)
            
            # تحليل نقاط القوة والضعف
            strengths_weaknesses = self._analyze_academic_strengths_weaknesses(
                data.get('course_recommendations', {}),
                academic_performance
            )
            
            return {
                'gpa_trend': gpa_trend,
                'learning_style': preferred_learning_style,
                'strengths': strengths_weaknesses.get('strengths', []),
                'weaknesses': strengths_weaknesses.get('weaknesses', []),
                'optimal_study_load': self._calculate_optimal_study_load(academic_performance),
                'best_performance_periods': self._identify_best_performance_periods(academic_performance),
                'learning_efficiency': self._calculate_learning_efficiency(academic_performance)
            }
            
        except Exception as e:
            return {'error': f'خطأ في تحليل أنماط التعلم: {str(e)}'}
    
    def _determine_learning_style(self, performance_data):
        """تحديد نمط التعلم المفضل"""
        if not performance_data:
            return 'غير محدد'
        
        gpa_trend = performance_data.get('gpa_trend', 'مستقر')
        performance_level = performance_data.get('performance_level', 'متوسط')
        
        if gpa_trend == 'متحسن':
            return 'تعلم تدريجي - يحتاج وقت للتكيف'
        elif gpa_trend == 'متراجع':
            return 'يحتاج دعم إضافي ومتابعة'
        elif performance_level == 'ممتاز':
            return 'متعلم متميز ومستقل'
        else:
            return 'متعلم متوازن'
    
    def _analyze_academic_strengths_weaknesses(self, course_recommendations, performance_data):
        """تحليل نقاط القوة والضعف الأكاديمية"""
        strengths = []
        weaknesses = []
        
        # تحليل من بيانات الأداء
        if performance_data:
            performance_level = performance_data.get('performance_level', '')
            if performance_level == 'ممتاز':
                strengths.append('أداء أكاديمي متميز')
            elif performance_level == 'جيد جداً':
                strengths.append('أداء أكاديمي جيد')
            elif performance_level in ['ضعيف', 'مقبول']:
                weaknesses.append('يحتاج تحسين في الأداء العام')
            
            gpa_trend = performance_data.get('gpa_trend', '')
            if gpa_trend == 'متحسن':
                strengths.append('قدرة على التطوير والتحسن')
            elif gpa_trend == 'متراجع':
                weaknesses.append('تراجع في الأداء يحتاج معالجة')
        
        return {
            'strengths': strengths if strengths else ['يحتاج تقييم أعمق'],
            'weaknesses': weaknesses if weaknesses else ['لا توجد نقاط ضعف واضحة']
        }
    
    def _calculate_optimal_study_load(self, performance_data):
        """حساب الحمل الدراسي الأمثل"""
        if not performance_data:
            return {'recommended_credits': 15, 'reasoning': 'الحمل الدراسي المعياري'}
        
        performance_level = performance_data.get('performance_level', 'متوسط')
        
        if performance_level == 'ممتاز':
            return {'recommended_credits': 18, 'reasoning': 'أداء ممتاز يسمح بحمل دراسي أعلى'}
        elif performance_level == 'جيد جداً':
            return {'recommended_credits': 16, 'reasoning': 'أداء جيد يسمح بحمل دراسي معتدل'}
        elif performance_level in ['ضعيف', 'مقبول']:
            return {'recommended_credits': 12, 'reasoning': 'حمل دراسي مخفف للتركيز على التحسن'}
        else:
            return {'recommended_credits': 15, 'reasoning': 'الحمل الدراسي المعياري'}
    
    def _identify_best_performance_periods(self, performance_data):
        """تحديد فترات الأداء الأفضل"""
        if not performance_data:
            return 'غير محدد'
        
        semester_gpas = performance_data.get('semester_gpas', [])
        if semester_gpas:
            best_gpa = max(semester_gpas)
            best_semester_index = semester_gpas.index(best_gpa) + 1
            return f'أفضل أداء في الفصل {best_semester_index} بمعدل {best_gpa:.2f}'
        
        return 'غير محدد'
    
    def _calculate_learning_efficiency(self, performance_data):
        """حساب كفاءة التعلم"""
        if not performance_data:
            return 60.0
        
        current_gpa = performance_data.get('current_cumulative_gpa', 0)
        
        if current_gpa >= 3.5:
            return 85.0
        elif current_gpa >= 3.0:
            return 75.0
        elif current_gpa >= 2.5:
            return 65.0
        else:
            return 50.0
    
    def _analyze_academic_risks(self, data):
        """تحليل المخاطر الأكاديمية"""
        try:
            path_data = data.get('basic_path', {})
            progress = path_data.get('progress', {})
            
            risks = []
            risk_level = 'منخفض'
            
            # تحليل المعدل التراكمي
            cumulative_gpa = progress.get('cumulative_gpa', {})
            current_gpa = cumulative_gpa.get('current_cumulative', 0)
            
            if current_gpa < 2.0:
                risks.append('المعدل التراكمي أقل من الحد الأدنى')
                risk_level = 'عالي جداً'
            elif current_gpa < 2.5:
                risks.append('المعدل التراكمي منخفض')
                risk_level = 'عالي'
            elif current_gpa < 3.0:
                risks.append('المعدل التراكمي يحتاج تحسين')
                risk_level = 'متوسط'
            
            # تحليل اتجاه الأداء
            gpa_trend = cumulative_gpa.get('trend', 'مستقر')
            if gpa_trend == 'متراجع':
                risks.append('اتجاه الأداء متراجع')
                if risk_level == 'منخفض':
                    risk_level = 'متوسط'
            
            # تحليل الإنذارات الأكاديمية
            warnings_data = data.get('academic_warnings', [])
            if warnings_data and len(warnings_data) > 0:
                # تحويل كائنات الإنذارات إلى قاموس لتجنب مشكلة JSON
                active_warnings = []
                for warning in warnings_data:
                    if hasattr(warning, '__dict__'):
                        warning_dict = {
                            'id': getattr(warning, 'Id', None),
                            'type': getattr(warning, 'WarningType', ''),
                            'level': getattr(warning, 'WarningLevel', 0),
                            'status': getattr(warning, 'Status', '')
                        }
                        if warning_dict['status'] == 'نشط':
                            active_warnings.append(warning_dict)
                    elif isinstance(warning, dict):
                        if warning.get('status') == 'نشط':
                            active_warnings.append(warning)
                
                if active_warnings:
                    risks.append(f'يوجد {len(active_warnings)} إنذار أكاديمي نشط')
                    risk_level = 'عالي'
            
            return {
                'level': risk_level,
                'factors': risks,
                'mitigation_strategies': self._generate_risk_mitigation_strategies(risks, risk_level)
            }
            
        except Exception as e:
            return {
                'level': 'غير محدد',
                'factors': [],
                'mitigation_strategies': [],
                'error': f'خطأ في تحليل المخاطر: {str(e)}'
            }
    
    def _generate_risk_mitigation_strategies(self, risks, risk_level):
        """توليد استراتيجيات تخفيف المخاطر"""
        strategies = []
        
        if 'المعدل التراكمي' in str(risks):
            strategies.extend([
                'وضع خطة دراسية مكثفة',
                'طلب المساعدة من المرشد الأكاديمي',
                'التركيز على المواد الأساسية'
            ])
        
        if 'إنذار أكاديمي' in str(risks):
            strategies.extend([
                'مراجعة عاجلة مع المرشد الأكاديمي',
                'تقليل عدد الساعات المسجلة',
                'الاستفادة من برامج الدعم الأكاديمي'
            ])
        
        if 'اتجاه متراجع' in str(risks):
            strategies.extend([
                'تحليل أسباب التراجع',
                'تغيير استراتيجيات الدراسة',
                'طلب المساعدة النفسية إذا لزم الأمر'
            ])
        
        return strategies if strategies else ['المتابعة المستمرة للأداء الأكاديمي']
    
    def _predict_future_paths(self, comprehensive_data, ai_analysis):
        """التنبؤ بالمسارات المستقبلية"""
        try:
            predictions = {
                'academic_trajectory': self._predict_academic_trajectory(comprehensive_data, ai_analysis),
                'career_pathways': self._predict_career_pathways(comprehensive_data, ai_analysis),
                'skill_development': self._predict_skill_development(comprehensive_data, ai_analysis),
                'challenges_opportunities': self._predict_challenges_opportunities(comprehensive_data, ai_analysis)
            }
            
            return predictions
            
        except Exception as e:
            return {'error': f'خطأ في التنبؤ بالمسارات المستقبلية: {str(e)}'}
    
    def _predict_academic_trajectory(self, data, ai_analysis):
        """التنبؤ بالمسار الأكاديمي"""
        performance_prediction = ai_analysis.get('performance_prediction', {})
        
        return {
            'expected_gpa_trend': performance_prediction.get('trend_prediction', 'استقرار متوقع'),
            'graduation_timeline': performance_prediction.get('graduation_prediction', 'غير محدد'),
            'academic_milestones': [
                'إكمال متطلبات التشعيب',
                'تحقيق المعدل المطلوب للتخرج',
                'إنجاز مشروع التخرج'
            ]
        }
    
    def _predict_career_pathways(self, data, ai_analysis):
        """التنبؤ بالمسارات المهنية"""
        career_alignment = ai_analysis.get('career_alignment', {})
        
        return {
            'primary_career_path': career_alignment.get('current_path_prospects', {}).get('fields', ['غير محدد'])[0] if career_alignment.get('current_path_prospects', {}).get('fields') else 'غير محدد',
            'alternative_paths': career_alignment.get('current_path_prospects', {}).get('fields', [])[:3],
            'market_outlook': career_alignment.get('market_trends', 'اتجاهات متوازنة'),
            'skill_requirements': career_alignment.get('skill_gaps', [])
        }
    
    def _predict_skill_development(self, data, ai_analysis):
        """التنبؤ بتطوير المهارات"""
        career_alignment = ai_analysis.get('career_alignment', {})
        
        return {
            'technical_skills': career_alignment.get('skill_gaps', [])[:3],
            'soft_skills': ['التواصل الفعال', 'العمل الجماعي', 'حل المشكلات'],
            'development_timeline': 'تطوير تدريجي خلال السنوات المتبقية',
            'learning_resources': ['دورات تدريبية', 'مشاريع عملية', 'تدريب صيفي']
        }
    
    def _predict_challenges_opportunities(self, data, ai_analysis):
        """التنبؤ بالتحديات والفرص"""
        opportunities_threats = ai_analysis.get('opportunities_threats', {})
        
        return {
            'upcoming_challenges': opportunities_threats.get('threats', []),
            'potential_opportunities': opportunities_threats.get('opportunities', []),
            'preparation_strategies': [
                'التخطيط المسبق للتحديات',
                'بناء شبكة علاقات مهنية',
                'التطوير المستمر للمهارات'
            ]
        }
    
    def _generate_optimization_recommendations(self, comprehensive_data, ai_analysis, smart_plan):
        """توليد توصيات التحسين المستمر"""
        try:
            recommendations = {
                'performance_optimization': self._generate_performance_optimization(ai_analysis),
                'study_strategy_optimization': self._generate_study_strategy_optimization(ai_analysis),
                'career_preparation_optimization': self._generate_career_preparation_optimization(ai_analysis),
                'risk_management_optimization': self._generate_risk_management_optimization(ai_analysis),
                'continuous_improvement': self._generate_continuous_improvement_plan(ai_analysis)
            }
            
            return recommendations
            
        except Exception as e:
            return {'error': f'خطأ في توليد توصيات التحسين: {str(e)}'}
    
    def _generate_performance_optimization(self, ai_analysis):
        """توصيات تحسين الأداء"""
        learning_patterns = ai_analysis.get('learning_patterns', {})
        efficiency_analysis = ai_analysis.get('efficiency_analysis', {})
        
        recommendations = []
        
        # بناءً على أنماط التعلم
        learning_style = learning_patterns.get('learning_style', '')
        if 'يحتاج دعم' in learning_style:
            recommendations.append('طلب المساعدة الأكاديمية من الأساتذة')
            recommendations.append('الانضمام لمجموعات الدراسة')
        
        # بناءً على الكفاءة
        efficiency_level = efficiency_analysis.get('efficiency_level', '')
        if efficiency_level in ['مقبول', 'يحتاج تحسين']:
            recommendations.append('تحسين تقنيات الدراسة والمراجعة')
            recommendations.append('وضع جدول زمني منتظم للدراسة')
        
        return recommendations if recommendations else ['الحفاظ على الأداء الحالي الجيد']
    
    def _generate_study_strategy_optimization(self, ai_analysis):
        """توصيات تحسين استراتيجية الدراسة"""
        learning_patterns = ai_analysis.get('learning_patterns', {})
        
        optimal_load = learning_patterns.get('optimal_study_load', {})
        recommended_credits = optimal_load.get('recommended_credits', 15)
        
        return [
            f'تسجيل {recommended_credits} ساعة معتمدة كحد أمثل',
            'توزيع المقررات بتوازن بين الصعبة والسهلة',
            'التركيز على المقررات الأساسية أولاً',
            'استغلال فترات الأداء الأفضل للمقررات الصعبة'
        ]
    
    def _generate_career_preparation_optimization(self, ai_analysis):
        """توصيات تحسين التحضير المهني"""
        career_alignment = ai_analysis.get('career_alignment', {})
        career_development = career_alignment.get('career_development', [])
        
        recommendations = career_development.copy()
        
        # إضافة توصيات عامة
        recommendations.extend([
            'بناء محفظة أعمال قوية',
            'التدريب في الشركات ذات الصلة',
            'حضور المؤتمرات والفعاليات المهنية'
        ])
        
        return recommendations[:5]  # أول 5 توصيات
    
    def _generate_risk_management_optimization(self, ai_analysis):
        """توصيات تحسين إدارة المخاطر"""
        risk_analysis = ai_analysis.get('risk_analysis', {})
        mitigation_strategies = risk_analysis.get('mitigation_strategies', [])
        
        recommendations = mitigation_strategies.copy()
        
        # إضافة استراتيجيات وقائية
        recommendations.extend([
            'المراجعة الدورية للأداء الأكاديمي',
            'التواصل المستمر مع المرشد الأكاديمي',
            'وضع خطط بديلة للطوارئ'
        ])
        
        return recommendations
    
    def _generate_continuous_improvement_plan(self, ai_analysis):
        """خطة التحسين المستمر"""
        overall_score = ai_analysis.get('overall_ai_score', {})
        current_level = overall_score.get('level', 'متوسط')
        
        improvement_plan = {
            'current_level': current_level,
            'target_level': self._get_target_level(current_level),
            'improvement_actions': self._get_improvement_actions(current_level),
            'monitoring_frequency': 'شهرياً',
            'review_schedule': 'نهاية كل فصل دراسي'
        }
        
        return improvement_plan
    
    def _get_target_level(self, current_level):
        """تحديد المستوى المستهدف"""
        level_progression = {
            'يحتاج تحسين': 'مقبول',
            'مقبول': 'جيد',
            'جيد': 'جيد جداً',
            'جيد جداً': 'ممتاز',
            'ممتاز': 'ممتاز (الحفاظ على التميز)'
        }
        
        return level_progression.get(current_level, 'جيد')
    
    def _get_improvement_actions(self, current_level):
        """إجراءات التحسين حسب المستوى"""
        actions_map = {
            'يحتاج تحسين': [
                'وضع خطة دراسية مكثفة',
                'طلب المساعدة الأكاديمية',
                'تقليل الأنشطة الخارجية'
            ],
            'مقبول': [
                'تحسين تقنيات الدراسة',
                'زيادة ساعات المراجعة',
                'المشاركة في الأنشطة الأكاديمية'
            ],
            'جيد': [
                'التركيز على التميز في التخصص',
                'المشاركة في البحث العلمي',
                'تطوير المهارات القيادية'
            ],
            'جيد جداً': [
                'الحفاظ على التميز',
                'مساعدة الزملاء الآخرين',
                'التحضير للدراسات العليا'
            ],
            'ممتاز': [
                'الحفاظ على التميز المستمر',
                'قيادة المشاريع الأكاديمية',
                'التحضير للمنح الدراسية'
            ]
        }
        
        return actions_map.get(current_level, ['التطوير المستمر للمهارات'])
    
    def _generate_smart_plan(self, comprehensive_data, ai_analysis):
        """توليد الخطة الذكية المخصصة"""
        try:
            # الخطة قصيرة المدى (الفصل الحالي والقادم)
            short_term_plan = self._generate_short_term_plan(comprehensive_data, ai_analysis)
            
            # الخطة متوسطة المدى (السنة الأكاديمية)
            medium_term_plan = self._generate_medium_term_plan(comprehensive_data, ai_analysis)
            
            # الخطة طويلة المدى (حتى التخرج)
            long_term_plan = self._generate_long_term_plan(comprehensive_data, ai_analysis)
            
            # خطة الطوارئ
            contingency_plan = self._generate_contingency_plan(comprehensive_data, ai_analysis)
            
            return {
                'short_term': short_term_plan,
                'medium_term': medium_term_plan,
                'long_term': long_term_plan,
                'contingency': contingency_plan,
                'plan_summary': self._generate_plan_summary(
                    short_term_plan, medium_term_plan, long_term_plan
                )
            }
            
        except Exception as e:
            return {'error': f'خطأ في توليد الخطة الذكية: {str(e)}'}
    
    def _generate_short_term_plan(self, data, ai_analysis):
        """توليد الخطة قصيرة المدى"""
        plan = {
            'timeframe': 'الفصل الحالي والقادم',
            'priorities': [],
            'actions': [],
            'courses': [],
            'goals': []
        }
        
        # تحليل المخاطر الفورية
        risk_analysis = ai_analysis.get('risk_analysis', {})
        risk_level = risk_analysis.get('level', 'منخفض')
        
        if risk_level in ['عالي', 'عالي جداً']:
            plan['priorities'].append('معالجة المخاطر الأكاديمية الفورية')
            plan['actions'].extend(risk_analysis.get('mitigation_strategies', []))
        
        # تحليل الكفاءة الأكاديمية
        efficiency = ai_analysis.get('efficiency_analysis', {})
        improvement_areas = efficiency.get('improvement_areas', [])
        plan['actions'].extend(improvement_areas)
        
        # أهداف قصيرة المدى
        learning_patterns = ai_analysis.get('learning_patterns', {})
        optimal_load = learning_patterns.get('optimal_study_load', {})
        plan['goals'].append(f"تسجيل {optimal_load.get('recommended_credits', 15)} ساعة معتمدة")
        
        return plan
    
    def _generate_medium_term_plan(self, data, ai_analysis):
        """توليد الخطة متوسطة المدى"""
        plan = {
            'timeframe': 'السنة الأكاديمية الحالية',
            'priorities': [],
            'actions': [],
            'milestones': [],
            'goals': []
        }
        
        # تحليل التوافق المهني
        career_alignment = ai_analysis.get('career_alignment', {})
        career_development = career_alignment.get('career_development', [])
        plan['actions'].extend(career_development)
        
        # معالم متوسطة المدى
        path_data = data.get('basic_path', {})
        current_semester = path_data.get('student_info', {}).get('current_semester', 1)
        
        if current_semester <= 4:
            plan['milestones'].append('اختيار التشعيب النهائي')
        elif current_semester <= 6:
            plan['milestones'].append('التركيز على المقررات التخصصية')
        else:
            plan['milestones'].append('التحضير لمشروع التخرج')
        
        return plan
    
    def _generate_long_term_plan(self, data, ai_analysis):
        """توليد الخطة طويلة المدى"""
        plan = {
            'timeframe': 'حتى التخرج والمستقبل المهني',
            'priorities': [],
            'actions': [],
            'career_goals': [],
            'graduation_strategy': []
        }
        
        # استراتيجية التخرج
        performance_prediction = ai_analysis.get('performance_prediction', {})
        graduation_prediction = performance_prediction.get('graduation_prediction', '')
        plan['graduation_strategy'].append(f'التخرج المتوقع: {graduation_prediction}')
        
        # الأهداف المهنية
        career_alignment = ai_analysis.get('career_alignment', {})
        career_prospects = career_alignment.get('current_path_prospects', {})
        fields = career_prospects.get('fields', [])
        plan['career_goals'].extend(fields[:3])  # أول 3 مجالات
        
        # الفرص والتهديدات
        opportunities_threats = ai_analysis.get('opportunities_threats', {})
        opportunities = opportunities_threats.get('opportunities', [])
        plan['actions'].extend(opportunities)
        
        return plan
    
    def _generate_contingency_plan(self, data, ai_analysis):
        """توليد خطة الطوارئ"""
        plan = {
            'risk_scenarios': [],
            'mitigation_actions': [],
            'alternative_paths': [],
            'emergency_contacts': []
        }
        
        # سيناريوهات المخاطر
        risk_analysis = ai_analysis.get('risk_analysis', {})
        risks = risk_analysis.get('risks', [])
        plan['risk_scenarios'] = risks
        
        # إجراءات التخفيف
        mitigation_strategies = risk_analysis.get('mitigation_strategies', [])
        plan['mitigation_actions'] = mitigation_strategies
        
        # المسارات البديلة
        division_recommendations = data.get('division_recommendations', {})
        if division_recommendations and 'recommendations' in division_recommendations:
            recommendations = division_recommendations['recommendations']
            alternative_divisions = [rec for rec in recommendations if rec.get('suitability_score', 0) >= 60]
            plan['alternative_paths'] = [div.get('division_name', '') for div in alternative_divisions[:3]]
        
        # جهات الاتصال في الطوارئ
        plan['emergency_contacts'] = [
            'المرشد الأكاديمي',
            'شؤون الطلاب',
            'عمادة الكلية'
        ]
        
        return plan
    
    def _generate_plan_summary(self, short_term, medium_term, long_term):
        """توليد ملخص الخطة"""
        summary = {
            'key_priorities': [],
            'critical_actions': [],
            'success_factors': [],
            'timeline_overview': {}
        }
        
        # الأولويات الرئيسية
        summary['key_priorities'].extend(short_term.get('priorities', [])[:2])
        summary['key_priorities'].extend(medium_term.get('priorities', [])[:2])
        
        # الإجراءات الحرجة
        summary['critical_actions'].extend(short_term.get('actions', [])[:3])
        summary['critical_actions'].extend(medium_term.get('actions', [])[:2])
        
        # عوامل النجاح
        summary['success_factors'] = [
            'الالتزام بالخطة الموضوعة',
            'المتابعة الدورية مع المرشد الأكاديمي',
            'التقييم المستمر للتقدم',
            'المرونة في التكيف مع التغييرات'
        ]
        
        # نظرة عامة على الجدول الزمني
        summary['timeline_overview'] = {
            'immediate': 'الفصل الحالي والقادم',
            'short_term': 'السنة الأكاديمية الحالية',
            'long_term': 'حتى التخرج والمستقبل المهني'
        }
        
        return summary
    
    def _analyze_career_alignment(self, comprehensive_data):
        """تحليل التوافق المهني"""
        try:
            path_data = comprehensive_data.get('basic_path', {})
            division_recommendations = comprehensive_data.get('division_recommendations', {})
            
            current_path = path_data.get('current_path', {})
            current_division = current_path.get('division_display_name', 'غير محدد')
            
            # تحليل التوافق مع المسار الحالي
            alignment_score = 75  # نقطة بداية متوسطة
            
            # تحليل الأداء في المسار الحالي
            progress = path_data.get('progress', {})
            cumulative_gpa = progress.get('cumulative_gpa', {})
            current_gpa = cumulative_gpa.get('current_cumulative', 0)
            
            if current_gpa >= 3.5:
                alignment_score += 15
            elif current_gpa >= 3.0:
                alignment_score += 10
            elif current_gpa < 2.5:
                alignment_score -= 20
            
            # تحليل التوصيات المتاحة
            career_recommendations = []
            if division_recommendations and 'recommendations' in division_recommendations:
                for rec in division_recommendations['recommendations'][:3]:
                    career_recommendations.append({
                        'division': rec.get('division_name', ''),
                        'suitability': rec.get('recommendation_level', ''),
                        'score': rec.get('suitability_score', 0)
                    })
            
            return {
                'current_alignment_score': min(100, max(0, alignment_score)),
                'current_division': current_division,
                'alignment_level': self._get_alignment_level(alignment_score),
                'career_recommendations': career_recommendations,
                'market_trends': self._get_market_trends(),
                'skill_gaps': self._identify_skill_gaps(comprehensive_data)
            }
            
        except Exception as e:
            return {
                'current_alignment_score': 0,
                'current_division': 'غير محدد',
                'alignment_level': 'غير محدد',
                'career_recommendations': [],
                'error': f'خطأ في تحليل التوافق المهني: {str(e)}'
            }
    
    def _get_alignment_level(self, score):
        """تحديد مستوى التوافق"""
        if score >= 85:
            return 'ممتاز'
        elif score >= 70:
            return 'جيد'
        elif score >= 55:
            return 'مقبول'
        else:
            return 'يحتاج تحسين'
    
    def _get_market_trends(self):
        """الحصول على اتجاهات السوق"""
        return {
            'growing_fields': ['تقنية المعلومات', 'الذكاء الاصطناعي', 'علوم البيانات'],
            'stable_fields': ['الطب', 'الهندسة', 'التعليم'],
            'emerging_opportunities': ['الأمن السيبراني', 'الطاقة المتجددة', 'التكنولوجيا الحيوية']
        }
    
    def _identify_skill_gaps(self, comprehensive_data):
        """تحديد الفجوات في المهارات"""
        return [
            'مهارات التواصل',
            'مهارات القيادة',
            'مهارات تقنية متقدمة',
            'مهارات البحث العلمي'
        ]
    
    def _analyze_academic_efficiency(self, comprehensive_data):
        """تحليل الكفاءة الأكاديمية"""
        try:
            path_data = comprehensive_data.get('basic_path', {})
            progress = path_data.get('progress', {})
            
            # حساب الكفاءة بناءً على النسبة بين الساعات المكتملة والوقت المستغرق
            current_semester = progress.get('current_semester', 1)
            credits_completed = progress.get('credits_completed', 0)
            
            expected_credits = current_semester * 15  # متوسط 15 ساعة لكل فصل
            efficiency_ratio = (credits_completed / expected_credits * 100) if expected_credits > 0 else 0
            
            efficiency_level = 'ممتاز' if efficiency_ratio >= 90 else \
                             'جيد' if efficiency_ratio >= 75 else \
                             'مقبول' if efficiency_ratio >= 60 else 'ضعيف'
            
            return {
                'efficiency_ratio': round(efficiency_ratio, 2),
                'efficiency_level': efficiency_level,
                'credits_completed': credits_completed,
                'expected_credits': expected_credits,
                'improvement_suggestions': self._get_efficiency_suggestions(efficiency_ratio)
            }
            
        except Exception as e:
            return {
                'efficiency_ratio': 0,
                'efficiency_level': 'غير محدد',
                'error': f'خطأ في تحليل الكفاءة: {str(e)}'
            }
    
    def _get_efficiency_suggestions(self, efficiency_ratio):
        """اقتراحات لتحسين الكفاءة"""
        if efficiency_ratio < 60:
            return [
                'زيادة عدد الساعات المسجلة',
                'تحسين إدارة الوقت',
                'طلب المساعدة الأكاديمية'
            ]
        elif efficiency_ratio < 75:
            return [
                'تحسين استراتيجيات الدراسة',
                'تنظيم الجدول الدراسي'
            ]
        else:
            return [
                'الحفاظ على الأداء الحالي',
                'التفكير في ساعات إضافية'
            ]
    
    def _predict_future_performance(self, comprehensive_data):
        """التنبؤ بالأداء المستقبلي"""
        try:
            path_data = comprehensive_data.get('basic_path', {})
            progress = path_data.get('progress', {})
            cumulative_gpa = progress.get('cumulative_gpa', {})
            
            current_gpa = cumulative_gpa.get('current_cumulative', 0)
            gpa_trend = cumulative_gpa.get('trend', 'مستقر')
            
            # التنبؤ بالمعدل التراكمي للفصل القادم
            predicted_gpa = current_gpa
            if gpa_trend == 'متحسن':
                predicted_gpa += 0.2
            elif gpa_trend == 'متراجع':
                predicted_gpa -= 0.1
            
            predicted_gpa = min(4.0, max(0.0, predicted_gpa))
            
            # مستوى الثقة في التنبؤ
            confidence_level = 80 if gpa_trend != 'مستقر' else 70
            
            return {
                'predicted_next_gpa': round(predicted_gpa, 2),
                'confidence_level': confidence_level,
                'trend_direction': gpa_trend,
                'performance_outlook': self._get_performance_outlook(predicted_gpa, gpa_trend)
            }
            
        except Exception as e:
            return {
                'predicted_next_gpa': 0,
                'confidence_level': 0,
                'error': f'خطأ في التنبؤ بالأداء: {str(e)}'
            }
    
    def _get_performance_outlook(self, predicted_gpa, trend):
        """تحديد توقعات الأداء"""
        if predicted_gpa >= 3.5:
            return 'ممتاز - أداء متميز متوقع'
        elif predicted_gpa >= 3.0:
            return 'جيد - أداء مستقر متوقع'
        elif predicted_gpa >= 2.5:
            return 'مقبول - يحتاج تحسين'
        else:
            return 'ضعيف - يحتاج تدخل عاجل'
    
    def _analyze_opportunities_threats(self, comprehensive_data):
        """تحليل الفرص والتهديدات"""
        try:
            path_data = comprehensive_data.get('basic_path', {})
            progress = path_data.get('progress', {})
            
            opportunities = []
            threats = []
            
            # تحليل الفرص
            cumulative_gpa = progress.get('cumulative_gpa', {})
            current_gpa = cumulative_gpa.get('current_cumulative', 0)
            
            if current_gpa >= 3.5:
                opportunities.extend([
                    'التقدم للمنح الدراسية',
                    'الانضمام لبرامج التميز',
                    'فرص البحث العلمي'
                ])
            
            if current_gpa >= 3.0:
                opportunities.extend([
                    'التدريب في شركات مرموقة',
                    'المشاركة في المؤتمرات العلمية'
                ])
            
            # تحليل التهديدات
            gpa_trend = cumulative_gpa.get('trend', 'مستقر')
            if gpa_trend == 'متراجع':
                threats.append('تراجع الأداء الأكاديمي')
            
            if current_gpa < 2.5:
                threats.extend([
                    'خطر الإنذار الأكاديمي',
                    'صعوبة في الحصول على فرص تدريب'
                ])
            
            return {
                'opportunities': opportunities,
                'threats': threats,
                'strategic_recommendations': self._get_strategic_recommendations(opportunities, threats)
            }
            
        except Exception as e:
            return {
                'opportunities': [],
                'threats': [],
                'error': f'خطأ في تحليل الفرص والتهديدات: {str(e)}'
            }
    
    def _get_strategic_recommendations(self, opportunities, threats):
        """التوصيات الاستراتيجية"""
        recommendations = []
        
        if opportunities:
            recommendations.append('استغلال الفرص المتاحة لتطوير المسار المهني')
        
        if threats:
            recommendations.append('وضع خطة لمواجهة التحديات المحتملة')
        
        recommendations.extend([
            'التطوير المستمر للمهارات',
            'بناء شبكة علاقات مهنية',
            'المتابعة الدورية للأداء الأكاديمي'
        ])
        
        return recommendations
    
    def _calculate_overall_ai_score(self, learning_patterns, risk_analysis, career_alignment, efficiency_analysis, performance_prediction):
        """حساب النقاط الإجمالية للذكاء الاصطناعي"""
        try:
            scores = []
            
            # نقاط من تحليل أنماط التعلم
            if learning_patterns.get('learning_efficiency', 0) > 0:
                scores.append(learning_patterns['learning_efficiency'])
            
            # نقاط من تحليل المخاطر (عكسي)
            risk_level = risk_analysis.get('level', 'متوسط')
            risk_score = {'منخفض': 90, 'متوسط': 70, 'عالي': 40, 'عالي جداً': 20}.get(risk_level, 50)
            scores.append(risk_score)
            
            # نقاط من التوافق المهني
            if career_alignment.get('current_alignment_score', 0) > 0:
                scores.append(career_alignment['current_alignment_score'])
            
            # نقاط من الكفاءة الأكاديمية
            if efficiency_analysis.get('efficiency_ratio', 0) > 0:
                scores.append(min(100, efficiency_analysis['efficiency_ratio']))
            
            # نقاط من التنبؤ بالأداء
            confidence = performance_prediction.get('confidence_level', 0)
            if confidence > 0:
                scores.append(confidence)
            
            overall_score = sum(scores) / len(scores) if scores else 0
            
            return {
                'score': round(overall_score, 2),
                'level': 'ممتاز' if overall_score >= 85 else 'جيد' if overall_score >= 70 else 'مقبول' if overall_score >= 55 else 'يحتاج تحسين',
                'components': {
                    'learning_patterns': learning_patterns.get('learning_efficiency', 0),
                    'risk_management': risk_score,
                    'career_alignment': career_alignment.get('current_alignment_score', 0),
                    'academic_efficiency': efficiency_analysis.get('efficiency_ratio', 0),
                    'prediction_confidence': confidence
                }
            }
            
        except Exception as e:
            return {
                'score': 0,
                'level': 'غير محدد',
                'error': f'خطأ في حساب النقاط: {str(e)}'
            }