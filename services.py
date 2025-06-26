from datetime import datetime
from sqlalchemy import func, and_, or_
from extensions import db
from models import (
    Students, Divisions, Enrollments, Courses, CourseDivisions, Departments,
    AcademicWarnings, Attendances, EnrollmentPeriods, CoursePrerequisites, Classes, Professors
)

from functools import lru_cache
import time
from sqlalchemy.orm import joinedload, selectinload
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import statistics
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pandas as pd
import logging

logger = logging.getLogger(__name__)






class GraduationEligibilityService:
    
   
    TOTAL_REQUIRED_CREDITS = 136
    MANDATORY_CREDITS = 96
    ELECTIVE_CREDITS = 40
    MINIMUM_GPA = 2.0
    
    YEAR_CLASSIFICATIONS = {
        1: (0, 33),    
        2: (34, 67),    
        3: (68, 101),  
        4: (102, 136)  
    }
    
    ACADEMIC_TRACKS = {
        "العلوم الطبيعية": {
            "year_1": [1030],  
            "year_2": [1035, 1095],  
            "year_3_4_math_physics": [1040, 1045, 1035, 1050],
            "year_3_4_chem_physics": [1055, 1095]
        },
        "العلوم البيولوجية": {
            "year_1_2": [1085],  
            "year_3_4": [1060, 1065, 1070, 1075]
        },
        "العلوم الجيولوجية": {
            "year_1_2": [1090],  
            "year_3_4": [1080]
        }
    }

    # نظام التشعيب الأكاديمي المحدث
    DIVISION_SYSTEM = {
        # أكواد الشعب وما يقابلها من مسارات
        '1030': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الأولى', 
            'level': 1,
            'next_options': ['1035', '1095'],
            'description': 'مجموعة العلوم الطبيعية'
        },
        '1035': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الثانية', 
            'level': 2,
            'next_options': ['1040', '1045', '1035', '1050'],
            'description': 'الرياضيات والفيزياء'
        },
        '1095': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الثانية', 
            'level': 2,
            'next_options': ['1055', '1095'],
            'description': 'الكيمياء والفيزياء'
        },
        '1040': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'الرياضيات الخاصة'
        },
        '1045': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'الفيزياء الخاصة'
        },
        '1050': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'الرياضيات وعلوم الحاسب'
        },
        '1055': {
            'path': 'العلوم الطبيعية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'الكيمياء الخاصة'
        },
        '1085': {
            'path': 'العلوم البيولوجية', 
            'stage': 'السنة الأولى والثانية', 
            'level': 1,
            'next_options': ['1060', '1065', '1070', '1075'],
            'description': 'مجموعة العلوم البيولوجية والكيميائية'
        },
        '1060': {
            'path': 'العلوم البيولوجية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'علم الحيوان'
        },
        '1065': {
            'path': 'العلوم البيولوجية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'النبات والكيمياء'
        },
        '1070': {
            'path': 'العلوم البيولوجية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'علم الحيوان والكيمياء'
        },
        '1075': {
            'path': 'العلوم البيولوجية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'الكيمياء والكيمياء الحيوية'
        },
        '1090': {
            'path': 'العلوم الجيولوجية', 
            'stage': 'السنة الأولى والثانية', 
            'level': 1,
            'next_options': ['1080'],
            'description': 'مجموعة العلوم الجيولوجية والكيميائية'
        },
        '1080': {
            'path': 'العلوم الجيولوجية', 
            'stage': 'السنة الثالثة والرابعة', 
            'level': 3,
            'next_options': [],
            'description': 'الجيولوجيا والكيمياء'
        }
    }

    @classmethod
    def get_graduation_eligibility(cls, student_id):
        try:
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود"
                    
                }
            
            student_info = cls._get_student_info(student)
            
            cumulative_gpa = cls._calculate_gpa(student_id)
            
            completed_courses = cls._get_completed_courses(student_id)
            failed_courses = cls._get_failed_courses(student_id)
            remaining_courses = cls._get_remaining_courses(student_id, student.DivisionId)
            
            credits_analysis = cls._analyze_credits(
                completed_courses, 
                remaining_courses, 
                student.DivisionId,
                student.CreditsCompleted
            )
            
            gpa_analysis = cls._analyze_gpa(cumulative_gpa)
            
            warnings = cls._get_academic_warnings(student_id)
            
            graduation_status = cls._determine_graduation_status(
                credits_analysis, cumulative_gpa, warnings
            )
            
            graduation_planning = cls._calculate_graduation_planning(
                credits_analysis, student_info["current_semester"]
            )
            
            recommendations = cls._generate_recommendations(
                graduation_status, credits_analysis, gpa_analysis, remaining_courses, student_info
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
        academic_year = student.StudentLevel or 1
        
        division = Divisions.query.get(student.DivisionId)
        division_name = division.Name if division else "غير محدد"
        
        # تحديد مرحلة الطالب الأكاديمية
        academic_stage_info = GraduationEligibilityService._determine_academic_stage(student)
        
        return {
            "id": student.Id,
            "name": student.Name,
            "division": division_name,
            "division_code": str(student.DivisionId),
            "current_semester": student.Semester,
            "academic_year": academic_year,
            "status": student.status,
            "credits_completed": student.CreditsCompleted,
            "academic_stage": academic_stage_info
        }

    @staticmethod
    def _determine_academic_stage(student):
        """تحديد مرحلة الطالب الأكاديمية والمواد المطلوبة"""
        division_code = str(student.DivisionId)
        current_semester = student.Semester
        
        # التحقق من وجود الشعبة في النظام
        if division_code not in GraduationEligibilityService.DIVISION_SYSTEM:
            return {
                "stage": "غير محدد",
                "specialization_status": "غير معروف",
                "can_choose_specialization": False,
                "available_options": [],
                "message": "شعبة غير مسجلة في النظام"
            }
        
        division_info = GraduationEligibilityService.DIVISION_SYSTEM[division_code]
        
        # تحديد حالة التخصص بناءً على نوع الشعبة
        if division_info['level'] == 1:  # شعب عامة (يمكن اختيار تخصص منها)
            can_choose = current_semester >= 3  # يمكن الاختيار من الترم 3
            
            return {
                "stage": division_info['stage'],
                "path": division_info['path'],
                "specialization_status": "لم يتم اختيار التخصص النهائي بعد",
                "can_choose_specialization": can_choose,
                "available_options": division_info['next_options'],
                "message": f"الطالب في {division_info['description']} - يمكن اختيار التخصص النهائي"
            }
        else:  # شعب متخصصة (تخصص نهائي)
            return {
                "stage": division_info['stage'],
                "path": division_info['path'],
                "specialization_status": "في التخصص النهائي",
                "can_choose_specialization": False,
                "available_options": [],
                "message": f"الطالب في تخصص {division_info['description']}"
            }

    @staticmethod
    def _analyze_credits(completed_courses, remaining_courses, division_id, actual_credits=None):
        
        calculated_credits = sum(course["credits"] for course in completed_courses)
        
        if actual_credits and actual_credits > calculated_credits:
            completed_credits = actual_credits
            data_source = "ملف الطالب (بيانات مكتملة)"
            estimated_mandatory = min(GraduationEligibilityService.MANDATORY_CREDITS, int(actual_credits * 0.75))
            estimated_elective = actual_credits - estimated_mandatory
        else:
            completed_credits = calculated_credits
            data_source = "المواد المسجلة"
            estimated_mandatory = GraduationEligibilityService._calculate_mandatory_credits(completed_courses)
            estimated_elective = completed_credits - estimated_mandatory
        
        remaining_credits = sum(course["credits"] for course in remaining_courses)
        
        mandatory_remaining = 0
        elective_remaining = 0
        
        for course in remaining_courses:
            if course["type"] == "إجبارية":
                mandatory_remaining += course["credits"]
            else:
                elective_remaining += course["credits"]
        
        actual_mandatory_remaining = max(0, GraduationEligibilityService.MANDATORY_CREDITS - estimated_mandatory)
        actual_elective_remaining = max(0, GraduationEligibilityService.ELECTIVE_CREDITS - estimated_elective)
        
        total_remaining = max(0, GraduationEligibilityService.TOTAL_REQUIRED_CREDITS - completed_credits)
        
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
        try:
            mandatory_credits = 0
            for course in completed_courses:
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
        completed_courses = GraduationEligibilityService._get_completed_courses(student_id)
        
        remaining_courses = GraduationEligibilityService._get_remaining_courses(student_id, division_id)
        
        failed_courses = GraduationEligibilityService._get_failed_courses(student_id)
        
        return {
            "completed": completed_courses,
            "remaining": remaining_courses,
            "failed": failed_courses
        }

    @staticmethod
    def _get_completed_courses(student_id):
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
        try:
            student = Students.query.get(student_id)
            if not student:
                return []
                
            # تحديد مرحلة الطالب الأكاديمية
            academic_stage = GraduationEligibilityService._determine_academic_stage(student)
            
            enrolled_course_ids = db.session.query(Enrollments.CourseId).filter(
                Enrollments.StudentId == student_id,
                Enrollments.IsCompleted.in_(["مكتملة", "قيد الدراسة"])
            ).subquery()
            
            remaining_courses = []
            
            # إذا كان الطالب لم يختر تخصص نهائي بعد
            if academic_stage["specialization_status"] in ["لم يتم اختيار التخصص النهائي بعد", "يجب اختيار التخصص فوراً"]:
                # عرض المواد الحالية للشعبة الموجود فيها
                current_division_courses = db.session.query(Courses).join(
                    CourseDivisions, Courses.Id == CourseDivisions.CourseId
                ).filter(
                    CourseDivisions.DivisionId == division_id,
                    ~Courses.Id.in_(enrolled_course_ids)
                ).all()
                
                for course in current_division_courses:
                    division_course = db.session.query(CourseDivisions).filter(
                        CourseDivisions.DivisionId == division_id,
                        CourseDivisions.CourseId == course.Id
                    ).first()
                    
                    course_type = "إجبارية" if division_course and division_course.IsMandatory else "اختيارية"
                    is_available = course.Status == "متاح"
                    availability_status = "متاحة للتسجيل" if is_available else "غير متاحة حالياً"
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
                        "category": "مواد الشعبة الحالية"
                    })
                
                # إضافة معلومات عن التخصصات المتاحة
                if academic_stage["available_options"]:
                    available_specializations = []
                    for option_code in academic_stage["available_options"]:
                        if option_code in GraduationEligibilityService.DIVISION_SYSTEM:
                            spec_info = GraduationEligibilityService.DIVISION_SYSTEM[option_code]
                            available_specializations.append({
                                "code": option_code,
                                "name": spec_info["description"],
                                "path": spec_info["path"],
                                "stage": spec_info["stage"]
                            })
                    
                    # إضافة معلومة خاصة عن التخصصات المتاحة
                    remaining_courses.append({
                        "id": "SPECIALIZATION_INFO",
                        "name": "اختيار التخصص",
                        "code": "SPEC",
                        "credits": 0,
                        "type": "معلومات",
                        "availability_status": "متاح للاختيار" if academic_stage["can_choose_specialization"] else "غير متاح بعد",
                        "prerequisites": "إنهاء متطلبات الشعبة الحالية",
                        "semester": 0,
                        "category": "تخصصات متاحة",
                        "available_specializations": available_specializations
                    })
            
            else:
                # الطالب في تخصص نهائي - عرض المواد العادية
                division_courses = db.session.query(Courses).join(
                    CourseDivisions, Courses.Id == CourseDivisions.CourseId
                ).filter(
                    CourseDivisions.DivisionId == division_id,
                    ~Courses.Id.in_(enrolled_course_ids)
                ).all()
                
                for course in division_courses:
                    division_course = db.session.query(CourseDivisions).filter(
                        CourseDivisions.DivisionId == division_id,
                        CourseDivisions.CourseId == course.Id
                    ).first()
                    
                    course_type = "إجبارية" if division_course and division_course.IsMandatory else "اختيارية"
                    is_available = course.Status == "متاح"
                    availability_status = "متاحة للتسجيل" if is_available else "غير متاحة حالياً"
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
                        "category": "مواد التخصص"
                    })
            
            return remaining_courses
            
        except Exception as e:
            logger.error(f"Error getting remaining courses: {str(e)}")
            return []

    @staticmethod
    def _get_course_prerequisites(course_id, student_id):
        try:
            prerequisites = db.session.query(CoursePrerequisites, Courses).join(
                Courses, CoursePrerequisites.PrerequisiteCourseId == Courses.Id
            ).filter(
                CoursePrerequisites.CourseId == course_id
            ).all()
            
            if not prerequisites:
                return "لا توجد متطلبات سابقة"
            
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
                    "can_retake": True  
                }
                for enrollment, course in failed
            ]
        except Exception as e:
            logger.error(f"Error getting failed courses: {str(e)}")
            return []

    @staticmethod
    def _analyze_gpa(cumulative_gpa):
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
        """الحصول على الإنذارات الأكاديمية - مبسط"""
        try:
            active_warnings = AcademicWarnings.query.filter(
                AcademicWarnings.StudentId == student_id,
                AcademicWarnings.Status == "نشط"
            ).all()
            
            if not active_warnings:
                return {
                    "has_warnings": False,
                    "count": 0,
                    "types": []
                }
            
            warning_types = list(set([warning.WarningType for warning in active_warnings]))
            
            return {
                "has_warnings": True,
                "count": len(active_warnings),
                "types": warning_types
            }
        except Exception as e:
            logger.error(f"Error getting academic warnings: {str(e)}")
            return {
                "has_warnings": False,
                "count": 0,
                "types": []
            }

    @staticmethod
    def _determine_graduation_status(credits_analysis, cumulative_gpa, warnings):
        credits_complete = credits_analysis["remaining_total"] == 0
        
        gpa_meets_requirement = cumulative_gpa >= GraduationEligibilityService.MINIMUM_GPA
        
        has_active_warnings = warnings.get("has_warnings", False)
        
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
            warning_types_text = " و ".join(warnings.get("types", []))
            status = "مشروط - إنذارات أكاديمية"
            message = f"يجب حل الإنذارات الأكاديمية أولاً ({warning_types_text})"
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
        remaining_credits = credits_analysis["remaining_total"]
        
        if remaining_credits == 0:
            return {
                "semesters_remaining": 0,
                "expected_graduation_date": "مؤهل للتخرج الآن",
                "credits_per_semester": 0,
                "recommended_load": "لا توجد مواد متبقية"
            }
        
        average_credits_per_semester = 16
        semesters_remaining = max(1, (remaining_credits + average_credits_per_semester - 1) // average_credits_per_semester)
        
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
    def _generate_recommendations(graduation_status, credits_analysis, gpa_analysis, remaining_courses, student_info=None):
        recommendations = []
        
        # التحقق من وجود معلومات الطالب
        if student_info and "academic_stage" in student_info:
            academic_stage = student_info["academic_stage"]
            
            # توصيات خاصة بالطلاب اللي لسه مختاروش تخصص
            if academic_stage["specialization_status"] == "لم يتم اختيار التخصص النهائي بعد":
                if academic_stage["can_choose_specialization"]:
                    available_specs = [
                        GraduationEligibilityService.DIVISION_SYSTEM.get(opt, {}).get('description', opt) 
                        for opt in academic_stage.get('available_options', [])
                    ]
                    recommendations.append({
                        "type": "تخصص",
                        "priority": "عالية",
                        "message": f"يمكنك اختيار التخصص النهائي. التخصصات المتاحة: {', '.join(available_specs)}"
                    })
                else:
                    recommendations.append({
                        "type": "أكاديمي",
                        "priority": "متوسطة",
                        "message": f"أكمل مواد {academic_stage['stage']} أولاً قبل اختيار التخصص النهائي"
                    })
        
        # التوصيات العادية للتخرج
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
        
        # توصيات المواد المتاحة
        available_courses = [course for course in remaining_courses if course.get("availability_status") == "متاحة للتسجيل" and course.get("id") != "SPECIALIZATION_INFO"]
        if available_courses:
            mandatory_available = [c for c in available_courses if c.get("type") == "إجبارية"]
            if mandatory_available:
                recommendations.append({
                    "type": "تسجيل",
                    "priority": "عالية",
                    "message": f"يوجد {len(mandatory_available)} مادة إجبارية متاحة للتسجيل حالياً"
                })
        
        unavailable_courses = [course for course in remaining_courses if course.get("availability_status") != "متاحة للتسجيل" and course.get("id") != "SPECIALIZATION_INFO"]
        if unavailable_courses:
            recommendations.append({
                "type": "تخطيط",
                "priority": "متوسطة", 
                "message": f"يوجد {len(unavailable_courses)} مادة غير متاحة حالياً - خطط للفصول القادمة"
            })
        
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
            student = Students.query.get(student_id)
            if not student:
                return 0.0
            
            gpa_history = []
            for i in range(1, student.Semester + 1):
                gpa_field = f'GPA{i}'
                if hasattr(student, gpa_field) and getattr(student, gpa_field) is not None:
                    gpa_history.append(float(getattr(student, gpa_field)))
            
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

    def __init__(self):
        self.weights = {
            'content_based': 0.3,
            'academic_performance': 0.25,
            'schedule_optimization': 0.2,
            'prerequisite_analysis': 0.15,
            'gpa_improvement': 0.1
        }
    
    def _check_enrollment_period(self):
        """فحص ما إذا كانت فترة التسجيل مفتوحة أم لا"""
        try:
            current_date = datetime.now()
            
            # البحث عن فترة التسجيل الحالية
            active_period = EnrollmentPeriods.query.filter(
                EnrollmentPeriods.StartDate <= current_date,
                EnrollmentPeriods.EndDate >= current_date
            ).first()
            
            if active_period:
                return {
                    'is_open': True,
                    'message': f'فترة التسجيل مفتوحة حتى {active_period.EndDate.strftime("%Y-%m-%d")}',
                    'period_info': {
                        'semester': active_period.Semester,
                        'start_date': active_period.StartDate.strftime("%Y-%m-%d"),
                        'end_date': active_period.EndDate.strftime("%Y-%m-%d")
                    }
                }
            else:
                # البحث عن آخر فترة تسجيل انتهت
                last_period = EnrollmentPeriods.query.filter(
                    EnrollmentPeriods.EndDate < current_date
                ).order_by(EnrollmentPeriods.EndDate.desc()).first()
                
                if last_period:
                    return {
                        'is_open': False,
                        'message': f'فترة التسجيل انتهت في {last_period.EndDate.strftime("%Y-%m-%d")}',
                        'period_info': {
                            'semester': last_period.Semester,
                            'end_date': last_period.EndDate.strftime("%Y-%m-%d")
                        }
                    }
                else:
                    return {
                        'is_open': False,
                        'message': 'لا توجد فترة تسجيل محددة حالياً',
                        'period_info': None
                    }
                    
        except Exception as e:
            logger.error(f"Error checking enrollment period: {str(e)}")
            return {
                'is_open': False,
                'message': 'حدث خطأ أثناء فحص فترة التسجيل',
                'period_info': None
            }
    
    def get_smart_recommendations(self, student_id):
        try:
            # فحص فترة التسجيل أولاً
            enrollment_status = self._check_enrollment_period()
            
            if not enrollment_status['is_open']:
                return {
                    'enrollment_closed': True,
                    'message': enrollment_status['message'],
                    'period_info': enrollment_status['period_info'],
                    'recommendations_available': False
                }
            
            student_data = self._get_enhanced_student_data(student_id)
            if not student_data:
                return {"error": "الطالب غير موجود"}, 404
            
            academic_status = self._classify_student_academic_status(student_data)
            
            available_courses = self._get_available_courses(student_data)
            
            recommendations = self._generate_categorized_recommendations(
                student_data, available_courses, academic_status
            )
            
            # إضافة معلومات فترة التسجيل للتوصيات
            recommendations['enrollment_period'] = enrollment_status
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in smart recommendations: {str(e)}")
            return {"error": str(e)}, 500
    
    def _get_enhanced_student_data(self, student_id):
        try:
            student = Students.query.get(student_id)
            if not student:
                return None
            
            department_id = None
            if student.DivisionId:
                division = Divisions.query.get(student.DivisionId)
                if division:
                    department_id = division.DepartmentId
            
            current_gpa = self._get_current_gpa(student)
            
            completed_courses = self._get_completed_courses(student_id)
            failed_courses = self._get_failed_courses(student_id)
            currently_enrolled_course_ids = self._get_currently_enrolled_courses(student_id)
            
            performance_analysis = self._analyze_academic_performance(student)
            
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
        try:
            gpa_history = self._get_gpa_history(student)
            if gpa_history:
                return sum(gpa_history) / len(gpa_history)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting current GPA: {str(e)}")
            return 0.0
    
    def _get_gpa_history(self, student):
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
        try:
            enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted='مكتملة'
            ).all()
            
            completed_courses = []
            for enrollment in enrollments:
                course = Courses.query.get(enrollment.CourseId)
                if course:
                    exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                    exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                    final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                    total_grade = exam1_grade + exam2_grade + final_grade
                    
                    completed_courses.append({
                        'id': course.Id,
                        'name': course.Name,
                        'code': course.Code,
                        'credits': course.Credits,
                        'grade': total_grade,  
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
        try:
            # جلب المواد الراسب فيها
            failed_enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted='راسب'
            ).all()
            
            # جلب المواد المسجل فيها حالياً
            current_enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted='قيد الدراسة'
            ).all()
            
            currently_enrolled_course_ids = [enrollment.CourseId for enrollment in current_enrollments]
            
            # الحصول على بيانات الطالب للترم الحالي
            student = Students.query.get(student_id)
            current_semester_name = f"الترم {student.Semester}" if student else "الترم 1"
            
            failed_courses = []
            for enrollment in failed_enrollments:
                # تجاهل المواد الراسب فيها إذا كان مسجل فيها حالياً
                if enrollment.CourseId not in currently_enrolled_course_ids:
                    course = Courses.query.get(enrollment.CourseId)
                    if course:
                        is_mandatory = self._is_course_mandatory(course.Id, student_id)
                        
                        class_info = self._get_course_class_info(course.Id)
                        
                        # حساب عدد الطلاب المسجلين حالياً في نفس الترم
                        current_enrolled_count = db.session.query(Enrollments).filter(
                            Enrollments.CourseId == course.Id,
                            Enrollments.Semester == current_semester_name,
                            Enrollments.IsCompleted == 'قيد الدراسة'
                        ).count()
                        
                        failed_courses.append({
                            'id': course.Id,
                            'name': course.Name,
                            'code': course.Code,
                            'description': course.Description,
                            'credits': course.Credits,
                            'semester': course.Semester,
                            'is_mandatory': is_mandatory,
                            'max_seats': course.MaxSeats,
                            'current_enrolled': current_enrolled_count,  # العدد المحسوب من جدول Enrollments
                            'available_seats': course.MaxSeats - current_enrolled_count,
                            'professor_name': class_info.get('professor_name'),
                            'day_name': class_info.get('day'),
                            'start_time': class_info.get('start_time'),
                            'end_time': class_info.get('end_time'),
                            'location': class_info.get('location')
                        })
            
            return failed_courses
        except Exception as e:
            logger.error(f"Error getting failed courses: {str(e)}")
            return []
    
    def _is_course_mandatory(self, course_id, student_id):
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
        try:
            current_gpa = student_data['current_gpa']
            failed_courses_count = len(student_data['failed_courses'])
            gpa_history = student_data['gpa_history']
            
            gpa_trend = 'stable'
            if len(gpa_history) >= 2:
                if gpa_history[-1] > gpa_history[-2]:
                    gpa_trend = 'improving'
                elif gpa_history[-1] < gpa_history[-2]:
                    gpa_trend = 'declining'
            
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
        try:
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
                    exam1_grade = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                    exam2_grade = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                    final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                    total_grade = exam1_grade + exam2_grade + final_grade
                    
                    credits = course.Credits
                    
                    subject_type = 'general'  
                    
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
                'strengths': [],  
                'weaknesses': []  
            }
            
        except Exception as e:
            logger.error(f"Error analyzing academic performance: {str(e)}")
            return {}
    
    def _analyze_attendance_patterns(self, student_id):
        try:
            attendance_records = Attendances.query.filter_by(StudentId=student_id).all()
            
            if not attendance_records:
                return {'attendance_rate': 100, 'pattern': 'no_data'}
            
            total_sessions = len(attendance_records)
            attended_sessions = sum(1 for record in attendance_records if record.Status)
            attendance_rate = (attended_sessions / total_sessions) * 100
            
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
        try:
            available_courses = db.session.query(Courses).join(
                CourseDivisions, Courses.Id == CourseDivisions.CourseId
            ).filter(
                CourseDivisions.DivisionId == student_data['division_id'],
                Courses.Status == 'متاح'
            ).all()
            
            completed_course_ids = [course['id'] for course in student_data['completed_courses']]
            
            # الحصول على المواد المسجل فيها حالياً بتفاصيل أكثر
            current_enrollments = Enrollments.query.filter_by(
                StudentId=student_data['id'],
                IsCompleted='قيد الدراسة'
            ).all()
            
            currently_enrolled_course_ids = [enrollment.CourseId for enrollment in current_enrollments]
            
            # دمج المواد المكتملة والمسجل فيها حالياً
            excluded_course_ids = completed_course_ids + currently_enrolled_course_ids
            
            # الحصول على الترم الحالي للطالب
            current_semester_name = f"الترم {student_data['current_semester']}"
            
            filtered_courses = []
            for course in available_courses:
                if course.Id not in excluded_course_ids:
                    prerequisites_met = self._check_prerequisites(course.Id, completed_course_ids)
                    
                    if prerequisites_met:
                        course_division = CourseDivisions.query.filter_by(
                            CourseId=course.Id,
                            DivisionId=student_data['division_id']
                        ).first()
                        
                        class_info = self._get_course_class_info(course.Id)
                        
                        # حساب عدد الطلاب المسجلين حالياً في نفس الترم
                        current_enrolled_count = db.session.query(Enrollments).filter(
                            Enrollments.CourseId == course.Id,
                            Enrollments.Semester == current_semester_name,
                            Enrollments.IsCompleted == 'قيد الدراسة'
                        ).count()
                        
                        filtered_courses.append({
                            'id': course.Id,
                            'name': course.Name,
                            'code': course.Code,
                            'description': course.Description,
                            'credits': course.Credits,
                            'semester': course.Semester,
                            'is_mandatory': course_division.IsMandatory if course_division else False,
                            'max_seats': course.MaxSeats,
                            'current_enrolled': current_enrolled_count,  # العدد المحسوب من جدول Enrollments
                            'available_seats': course.MaxSeats - current_enrolled_count,
                            'professor_name': class_info.get('professor_name', 'غير محدد'),
                            'day': class_info.get('day', 'غير محدد'),
                            'day_name': class_info.get('day', 'غير محدد'),
                            'start_time': class_info.get('start_time', 'غير محدد'),
                            'end_time': class_info.get('end_time', 'غير محدد'),
                            'location': class_info.get('location', 'غير محدد')
                        })
            
            return filtered_courses
            
        except Exception as e:
            logger.error(f"Error getting available courses: {str(e)}")
            return []
    
    def _get_course_class_info(self, course_id):
        try:
            class_session = Classes.query.filter_by(CourseId=course_id).first()
            
            if not class_session:
                return {}
            
            professor = Professors.query.get(class_session.ProfessorId)
            
            return {
                'professor_name': professor.FullName if professor else 'غير محدد',
                'day': class_session.Day,
                'start_time': str(class_session.StartTime) if class_session.StartTime else 'غير محدد',
                'end_time': str(class_session.EndTime) if class_session.EndTime else 'غير محدد',
                'location': class_session.Location or 'غير محدد'
            }
            
        except Exception as e:
            logger.error(f"Error getting course class info: {str(e)}")
            return {}
    
    def _check_prerequisites(self, course_id, completed_course_ids):
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
        try:
            current_semester = student_data['current_semester']
            
            current_semester_mandatory = []
            elective_courses = []  
            
            for course in available_courses:
                if course['is_mandatory']:
                    if course['semester'] == current_semester:
                        current_semester_mandatory.append(course)
                else:
                    elective_courses.append(course)
            
            failed_mandatory_courses = [course for course in student_data['failed_courses'] if course['is_mandatory']]
            
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
        try:
            recommendations = []
            current_semester = student_data['current_semester']
            
            for course in mandatory_courses:
                priority_score = self._calculate_mandatory_priority(course, student_data)
                
                difficulty_score = self._estimate_course_difficulty(course, student_data)
                
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
            
            recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
            
            return recommendations  
            
        except Exception as e:
            logger.error(f"Error recommending mandatory courses: {str(e)}")
            return []
    
    def _recommend_failed_courses_retry(self, failed_courses, student_data, academic_status):
        try:
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
                priority_score = self._calculate_mandatory_priority(course, student_data)
                difficulty_score = self._estimate_course_difficulty(course, student_data)
                
                suggested_semester = self._suggest_optimal_semester(course, student_data, academic_status)
                
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
                high_grade_probability = self._calculate_high_grade_probability(course, student_data)
                
                ease_score = self._calculate_course_ease_score(course, student_data)
                
                gpa_impact = self._calculate_gpa_impact(course, student_data)
                
                if academic_status['status'] == 'at_risk':
                    min_ease_score = 0.4
                    min_probability = 0.5
                else:
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
            
            recommendations.sort(key=lambda x: x['gpa_impact'], reverse=True)
            
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
        try:
            recommendations = []
            
            for course in elective_courses:
                if not course['is_mandatory']:
                    content_similarity = self._calculate_content_similarity(course, student_data)                   
                    strength_alignment = self._calculate_strength_alignment(course, student_data)
                    
                    career_relevance = self._calculate_career_relevance(course, student_data)                   
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
        try:
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
                difficulty = 1.0 - (avg_grade / 150.0)
            else:
                difficulty = 0.5  
            
            return max(0.0, min(1.0, difficulty)) 
            
        except Exception as e:
            logger.error(f"Error estimating course difficulty: {str(e)}")
            return 0.5
    
    def _calculate_content_similarity(self, course, student_data):
        try:
            if not student_data['completed_courses']:
                return 0.5
            
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
        try:
            completed_courses = student_data.get('completed_courses', [])
            if not completed_courses:
                return 0.5
            
            total_grades = sum(course['grade'] for course in completed_courses)
            avg_grade = total_grades / len(completed_courses)
            
            performance_ratio = avg_grade / 150.0
            
            return min(performance_ratio, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating similar courses performance: {str(e)}")
            return 0.5 
class CourseEnrollmentService:
    
    @staticmethod
    def enroll_student_in_course(student_id, course_id):
        try:
            enrollment_check = CourseEnrollmentService._check_enrollment_period()
            if not enrollment_check["is_active"]:
                return {
                    "success": False,
                    "message": enrollment_check["message"]
                }
            
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود"
                }
            
            course = Courses.query.get(course_id)
            if not course:
                return {
                    "success": False,
                    "message": "المادة غير موجودة"
                }
            
            current_semester = CourseEnrollmentService._get_current_semester()
            
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
            
            credit_check = CourseEnrollmentService._check_credit_limit(student, course, current_semester)
            if not credit_check["allowed"]:
                return {
                    "success": False,
                    "message": credit_check["message"]
                }
            
            availability_check = CourseEnrollmentService._check_course_availability(student_id, course_id)
            if not availability_check["available"]:
                return {
                    "success": False,
                    "message": availability_check["message"]
                }
            
           
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
                NumberOFSemster=student.Semester,  
                AddedEnrollmentDate=datetime.now().date(),
                IsCompleted="قيد الدراسة",
                Exam1Grade=None,
                Exam2Grade=None,
                Grade=None
            )
            
            db.session.add(new_enrollment)
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
       
        try:
            enrollment = Enrollments.query.get(enrollment_id)
            if not enrollment:
                return {
                    "success": False,
                    "message": "التسجيل غير موجود"
                }
            
            if enrollment.IsCompleted != "قيد الدراسة":
                return {
                    "success": False,
                    "message": f"لا يمكن إلغاء هذا التسجيل. الحالة الحالية: {enrollment.IsCompleted}"
                }
            
            course = Courses.query.get(enrollment.CourseId)
            
            enrollment.DeletedEnrollmentDate = datetime.now().date()
            enrollment.IsCompleted = "ملغاة"
            
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
        try:
            enrollment = Enrollments.query.get(enrollment_id)
            if not enrollment:
                return {
                    "success": False,
                    "message": "التسجيل غير موجود"
                }
            
            course = Courses.query.get(enrollment.CourseId)
            course_name = course.Name if course else "غير محدد"
            course_code = course.Code if course else "غير محدد"
            
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
        try:
            student = Students.query.get(student_id)
            if not student:
                return {
                    "success": False,
                    "message": "الطالب غير موجود"
                }
            
            current_semester = CourseEnrollmentService._get_current_semester()
            
            enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                Semester=current_semester
            ).all()
            
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
        try:
            if hasattr(student, 'Semester') and student.Semester == 1:
                return 2.0  
            
            gpa_values = []
            
            for i in range(1, 9):  
                gpa_attr = f'GPA{i}'
                if hasattr(student, gpa_attr):
                    gpa_value = getattr(student, gpa_attr)
                    if gpa_value is not None and gpa_value > 0:
                        gpa_values.append(float(gpa_value))
            
            if gpa_values:
                return sum(gpa_values) / len(gpa_values)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in _calculate_average_gpa: {str(e)}")
            if hasattr(student, 'Semester') and student.Semester == 1:
                return 2.0
            return None
    
    @staticmethod
    def _check_enrollment_period():
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
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year
        
        if 2 <= current_month < 6:
            return f"ربيع {current_year}"
        elif 9 <= current_month <= 12:
            return f"خريف {current_year}"
        elif current_month == 1:
            return f"شتاء {current_year - 1}"
        else:
            return f"صيف {current_year}"
    
    @staticmethod
    def _check_credit_limit(student, course, current_semester):
        try:
            average_gpa = CourseEnrollmentService._calculate_average_gpa(student)
            max_credits = 18 if average_gpa and average_gpa >= 2.0 else 10
            
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
            
            new_course_credits = course.Credits or 0
            total_credits_after = current_credits + new_course_credits
            
            if total_credits_after > max_credits:
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
        try:
            course = Courses.query.get(course_id)
            if not course:
                return {
                    "available": False,
                    "message": "المادة غير موجودة"
                }
            
            if hasattr(course, 'Status') and course.Status != 'متاح':
                return {
                    "available": False,
                    "message": "المادة غير متاحة حالياً"
                }
            
            student = Students.query.get(student_id)
            if not student:
                return {
                    "available": False,
                    "message": "الطالب غير موجود"
                }
            
            division_check = CourseEnrollmentService._check_course_division_availability(student.DivisionId, course_id)
            if not division_check["available"]:
                return {
                    "available": False,
                    "message": division_check["message"]
                }
            
            prerequisite_check = CourseEnrollmentService._check_prerequisites(student_id, course_id)
            if not prerequisite_check["satisfied"]:
                return {
                    "available": False,
                    "message": prerequisite_check["message"]
                }
            
            if hasattr(course, 'MaxSeats') and course.MaxSeats:
                current_semester = CourseEnrollmentService._get_current_semester()
                
                current_enrolled_count = Enrollments.query.filter_by(
                    CourseId=course_id,
                    Semester=current_semester,
                    IsCompleted="قيد الدراسة"
                ).count()
                
                if current_enrolled_count >= course.MaxSeats:
                    return {
                        "available": False,
                        "message": f"المادة مكتملة العدد ({current_enrolled_count}/{course.MaxSeats})"
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
        try:
            course_division = CourseDivisions.query.filter_by(
                CourseId=course_id,
                DivisionId=division_id
            ).first()
            
            if not course_division:
                return {
                    "available": False,
                    "message": "المادة غير متاحة لشعبة الطالب"
                }
            
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
        try:
            prerequisites = CoursePrerequisites.query.filter_by(CourseId=course_id).all()
            
            if not prerequisites:
                return {
                    "satisfied": True,
                    "message": "لا توجد متطلبات سابقة للمادة"
                }
            
            completed_enrollments = Enrollments.query.filter_by(
                StudentId=student_id,
                IsCompleted="مكتملة"
            ).all()
            
            completed_course_ids = [enrollment.CourseId for enrollment in completed_enrollments]
            
            missing_prerequisites = []
            
            for prerequisite in prerequisites:
                if prerequisite.PrerequisiteCourseId not in completed_course_ids:
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
        current_date = datetime.now()
        current_month = current_date.month
        
        if 2 <= current_month <= 6:
            return 2
        elif 9 <= current_month <= 12 or current_month == 1:
            return 1
        else:
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
        try:
            existing_warning = AcademicWarnings.query.filter(
                and_(
                    AcademicWarnings.StudentId == student.Id,
                    AcademicWarnings.WarningType == warning['type'],
                    AcademicWarnings.Status == 'Active'
                )
            ).first()
            
            if existing_warning:
                if warning['level'] > existing_warning.WarningLevel:
                    return True
                else:
                    self.logger.info(f"إنذار مشابه موجود بالفعل للطالب {student.Name}: {warning['type']} - المستوى {existing_warning.WarningLevel}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"خطأ في فحص تكرار الإنذارات: {str(e)}")
            return True  

    def _create_warning(self, student, warning, semester):
        try:
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
        from datetime import datetime
        now = datetime.now()
        if now.month >= 9 or now.month <= 1:
            return f"خريف {now.year}"
        elif now.month >= 2 and now.month < 6:
            return f"ربيع {now.year}"
        else:
            return f"صيف {now.year}"

    def check_and_resolve_warnings(self, student_id):
        try:
            student = Students.query.get(student_id)
            if not student:
                return False
            
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
                
                if warning.WarningType == 'رسوب في المواد':
                    current_warnings = self._evaluate_student_warnings(student, self.get_current_semester())
                    failing_warning = None
                    
                    for w in current_warnings:
                        if w['type'] == 'رسوب في المواد':
                            failing_warning = w
                            break
                    
                    if not failing_warning:
                        should_resolve = True
                        resolution_reason = "تم النجاح في جميع المواد المطلوبة"
                    elif failing_warning['level'] < warning.WarningLevel - 1:
                        should_resolve = True
                        resolution_reason = f"تحسن الأداء - انخفض عدد المواد الراسب فيها"
                
                elif warning.WarningType == 'انخفاض المعدل التراكمي':
                    current_gpa = self._get_current_gpa(student)
                    if current_gpa and current_gpa >= 2.5:
                        should_resolve = True
                        resolution_reason = f"تحسن المعدل التراكمي إلى {current_gpa:.2f}"
                    elif current_gpa and current_gpa >= 2.0 and warning.WarningLevel >= 3:
                        should_resolve = True
                        resolution_reason = f"تحسن المعدل التراكمي إلى {current_gpa:.2f}"
                
                elif 'الساعات المعتمدة' in warning.WarningType:
                    credit_warning = self._check_credit_progress(student)
                    if not credit_warning:
                        should_resolve = True
                        resolution_reason = "تم استكمال الساعات المطلوبة"
                    elif credit_warning['level'] < warning.WarningLevel:
                        should_resolve = True
                        resolution_reason = "تحسن في عدد الساعات المكتملة"
                
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
    
    @staticmethod
    def get_comprehensive_analysis(student_id: int) -> Dict:
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
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
            
            
            if 'current_gpa' in gpa_trends:
                del gpa_trends['current_gpa']
            if 'current_gpa' in risk_assessment:
                del risk_assessment['current_gpa']
            if 'current_gpa' in predictions:
                del predictions['current_gpa']
            
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
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            completed_semester = student.Semester - 1
            
            if completed_semester <= 0:
                return {
                    "trend": "no_data",
                    "slope": 0,
                    "current_gpa": 0,
                    "interpretation": "الطالب لم يكمل أي فصل دراسي بعد"
                }
            
            gpa_history = []
            cumulative_gpas = []
            semesters = []
            
            total_gpa = 0.0
            
            for i in range(1, completed_semester + 1):
                semester_gpa = getattr(student, f'GPA{i}', None)
                if semester_gpa is not None:
                    gpa_history.append(float(semester_gpa))
                    total_gpa += float(semester_gpa)
                    cumulative_gpa = total_gpa / i
                    cumulative_gpas.append(cumulative_gpa)
                    semesters.append(i)
            
            if len(cumulative_gpas) < 2:
                return {
                    "trend": "insufficient_data",
                    
                    "current_gpa": cumulative_gpas[0] if cumulative_gpas else 0,
                    "interpretation": "بيانات غير كافية لتحديد الاتجاه"
                }
            
            X = np.array(semesters).reshape(-1, 1)
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
        try:
            enrollments = Enrollments.query.filter_by(StudentId=student_id).all()
            if not enrollments:
                return {"error": "No enrollment data found"}
            
            semester_performance = {}
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None):
                    
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    semester = enrollment.Semester
                    if semester not in semester_performance:
                        semester_performance[semester] = []
                    semester_performance[semester].append(percentage)
            
            semester_averages = {}
            for semester, grades in semester_performance.items():
                semester_averages[semester] = round(statistics.mean(grades), 2)
            
            credits_performance = {}
            for enrollment in enrollments:
                if (enrollment.Grade is not None and 
                    enrollment.Exam1Grade is not None and 
                    enrollment.Exam2Grade is not None and
                    hasattr(enrollment, 'course') and enrollment.course):
                    
                    total_grade = (float(enrollment.Exam1Grade) + 
                                 float(enrollment.Exam2Grade) + 
                                 float(enrollment.Grade))
                    percentage = (total_grade / 150.0) * 100
                    
                    credits = enrollment.course.Credits
                    if credits not in credits_performance:
                        credits_performance[credits] = []
                    credits_performance[credits].append(percentage)
            
            credits_averages = {}
            for credits, grades in credits_performance.items():
                credits_averages[credits] = round(statistics.mean(grades), 2)
            
            pattern = AcademicStatusAnalysisService._identify_performance_patterns(
                semester_averages, credits_averages
            )
            
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
        insights = {}
        
        try:
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
        suggestions = []
        
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
        try:
            warnings = AcademicWarnings.query.filter_by(StudentId=student_id).all()
            
            if not warnings:
                return {
                    "total_warnings": 0,
                    "active_warnings_count": 0,
                    "current_status": "لا توجد إنذارات",
                    "risk_level": "آمن",
                    "last_warning_date": None
                }
            
            active_warnings_count = 0
            last_warning_date = None
            
            for warning in warnings:
                is_resolved = getattr(warning, 'IsResolved', False)
                if not is_resolved:
                    active_warnings_count += 1
                
                if warning.IssueDate:
                    if last_warning_date is None or warning.IssueDate > last_warning_date:
                        last_warning_date = warning.IssueDate
            
            total_warnings = len(warnings)
            
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
        try:
            student = Students.query.get(student_id)
            if not student:
                return {"error": "Student not found"}
            
            student_division = student.DivisionId
            student_semester = student.Semester
            student_current_gpa = AcademicStatusAnalysisService._get_current_gpa(student)
            
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
            
            peer_gpas = []
            peer_data = []
            
            for peer in peers:
                peer_gpa = AcademicStatusAnalysisService._get_current_gpa(peer)
                if peer_gpa > 0:  
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












class AcademicPathPlanningService:
    """خدمة التخطيط الأكاديمي المحسنة للسرعة"""
    
    def __init__(self):
        # نظام الشعب والتشعيبات - محسن
        self.specialization_system = {
            'مجموعة العلوم البيولوجية والكيميائية': {
                'intermediate_specializations': ['الأحياء', 'الكيمياء', 'الكيمياء الحيوية'],
                'final_specializations': {
                    'الأحياء': ['علم الحيوان', 'علم النبات', 'علم الأحياء الدقيقة'],
                    'الكيمياء': ['الكيمياء التحليلية', 'الكيمياء العضوية', 'الكيمياء غير العضوية'],
                    'الكيمياء الحيوية': ['الكيمياء الحيوية الطبية', 'الكيمياء الحيوية الجزيئية']
                }
            },
            'مجموعة العلوم الجيولوجية والكيميائية': {
                'intermediate_specializations': ['الجيولوجيا', 'الكيمياء'],
                'final_specializations': {
                    'الجيولوجيا': ['الجيولوجيا التطبيقية', 'الجيولوجيا البيئية'],
                    'الكيمياء': ['الكيمياء التحليلية', 'الكيمياء الصناعية']
                }
            },
            'مجموعة العلوم الطبيعية': {
                'intermediate_specializations': ['الفيزياء', 'الرياضيات'],
                'final_specializations': {
                    'الفيزياء': ['الفيزياء النظرية', 'الفيزياء التطبيقية'],
                    'الرياضيات': ['الرياضيات البحتة', 'الرياضيات التطبيقية']
                }
            }
        }
        
        # إعدادات الكاش المحسنة - إضافة الكاش المفقود
        self._cache = {}
        self._cache_timeout = 300  # 5 دقائق
        self._performance_cache = {}  # كاش الأداء المفقود
        self._student_cache = {}      # كاش بيانات الطلاب  
        self._courses_cache = {}      # كاش المقررات

    # تحسين جذري لاستعلامات قاعدة البيانات
    @lru_cache(maxsize=200)
    def _get_student_data_bulk(self, student_id):
        """استعلام واحد شامل لكل بيانات الطالب - محسن جداً"""
        from models import Students, Enrollments
        
        # استعلام واحد يجلب كل شيء
        student = db.session.query(Students)\
            .options(joinedload(Students.division))\
            .filter_by(Id=student_id)\
            .first()
            
        if not student:
            return None
            
        # جلب التسجيلات مع المقررات في استعلام واحد
        enrollments = db.session.query(Enrollments)\
            .options(joinedload(Enrollments.course))\
            .filter_by(StudentId=student_id)\
            .all()
            
        return {
            'student': student,
            'enrollments': enrollments,
            'division': student.division
        }

    @lru_cache(maxsize=50)
    def _get_all_division_data_bulk(self, division_id):
        """جلب كل بيانات الشعبة في استعلام واحد - محسن جداً"""
        # استعلام واحد شامل
        course_divisions = db.session.query(CourseDivisions)\
            .options(
                joinedload(CourseDivisions.course).joinedload(Courses.department),
                joinedload(CourseDivisions.division)
            )\
            .filter_by(DivisionId=division_id)\
            .all()
            
        courses_data = []
        for cd in course_divisions:
            course = cd.course
            department = course.department
            courses_data.append({
                'course_id': course.Id,
                'name': course.Name,
                'code': course.Code,
                'credits': course.Credits,
                'semester': course.Semester,
                'is_mandatory': cd.IsMandatory,
                'description': course.Description,
                'department_id': course.DepartmentId,
                'department_name': department.Name,
                'subject_type': self._determine_subject_type_cached(department.Name.lower(), course.Name.lower())
            })
            
        return courses_data

    def _get_completed_course_ids_fast(self, enrollments):
        """استخراج المقررات المكتملة من البيانات الموجودة - سريع جداً"""
        completed_ids = []
        for enroll in enrollments:
            if enroll.Grade:
                # تحويل الدرجة إلى نص للتعامل مع Decimal objects
                grade_str = str(enroll.Grade).upper()
                if grade_str not in ['F', 'W', 'I']:
                    completed_ids.append(enroll.CourseId)
        return completed_ids

    def get_academic_plan(self, student_id):
        """الحصول على الخطة الأكاديمية الشاملة للطالب - محسن جذرياً"""
        start_time = time.time()
        
        try:
            # جلب كل البيانات في استعلام واحد - تحسين جذري
            student_data = self._get_student_data_bulk(student_id)
            if not student_data:
                return self._error_response('الطالب غير موجود')
            
            student = student_data['student']
            enrollments = student_data['enrollments']
            division = student_data['division']
            
            # معلومات الشعبة من الكاش المحسن
            division_info = {
                'division_name': division.Name,
                'division_id': division.Id
            }
            
            # جلب المقررات المتاحة - محسن
            available_courses = self._get_all_division_data_bulk(division.Id)
            completed_course_ids = self._get_completed_course_ids_fast(enrollments)
            
            # حساب المعدل من البيانات الموجودة - بدون استعلام إضافي
            gpa = self._calculate_gpa_from_enrollments(enrollments)
            max_credits = self._get_max_credits(gpa)
            
            plan = None
            
            # تحديد نوع الخطة حسب الشعبة - محسن
            if division.Name in ['مجموعة العلوم البيولوجية والكيميائية', 
                                'مجموعة العلوم الجيولوجية والكيميائية']:
                plan = self._create_optimized_biology_geology_plan(
                    student, division_info, available_courses, completed_course_ids, max_credits
                )
            elif division.Name == 'مجموعة العلوم الطبيعية':
                plan = self._create_optimized_natural_sciences_plan(
                    student, division_info, available_courses, completed_course_ids, max_credits
                )
            
            if plan:
                # تسجيل الوقت المستغرق
                end_time = time.time()
                execution_time = round(end_time - start_time, 2)
                plan['performance_info'] = {
                    'execution_time_seconds': execution_time,
                    'optimization_level': 'high',
                    'database_queries_reduced': True
                }
                
                return plan
            else:
                return self._error_response('نوع الشعبة غير مدعوم')
                
        except Exception as e:
            return self._error_response(f'خطأ في إنشاء الخطة الأكاديمية: {str(e)}')

    def _calculate_gpa_from_enrollments(self, enrollments):
        """حساب المعدل من التسجيلات مباشرة - بدون استعلام"""
        total_points = 0
        total_credits = 0
        
        grade_points = {
            'A+': 4.0, 'A': 4.0, 'A-': 3.7,
            'B+': 3.3, 'B': 3.0, 'B-': 2.7,
            'C+': 2.3, 'C': 2.0, 'C-': 1.7,
            'D+': 1.3, 'D': 1.0, 'F': 0.0
        }
        
        for enrollment in enrollments:
            if enrollment.Grade:
                # تحويل الدرجة إلى نص للتعامل مع Decimal objects
                grade_str = str(enrollment.Grade).strip()
                if grade_str in grade_points:
                    course_credits = enrollment.course.Credits if enrollment.course else 3
                    total_credits += course_credits
                    total_points += grade_points[grade_str] * course_credits
        
        return total_points / total_credits if total_credits > 0 else 0.0

    def _create_optimized_biology_geology_plan(self, student, division_info, available_courses, completed_course_ids, max_credits):
        """إنشاء خطة محسنة للعلوم البيولوجية والجيولوجية"""
        current_semester = student.Semester
        
        # تحديد المرحلة الحالية
        if current_semester <= 2:
            stage = 'عام'
        elif current_semester <= 4:
            stage = 'تشعيب متوسط'
        else:
            stage = 'تخصص نهائي'
        
        # تصفية المقررات المتاحة - معالجة سريعة
        available_courses_filtered = [
            course for course in available_courses 
            if course['course_id'] not in completed_course_ids
        ]
        
        # إنشاء خطة الترمات
        semester_plans = self._create_fast_semester_plans(
            student, stage, current_semester, available_courses_filtered, max_credits
        )
        
        return {
            'message': 'تم إنشاء الخطة الأكاديمية بنجاح',
            'status': 'success',
            'student_info': {
                'name': student.Name,
                'student_id': student.Id,
                'current_semester': current_semester,
                'division': division_info['division_name'],
                'current_stage': stage,
                'max_credits_per_semester': max_credits
            },
            'semester_plans': semester_plans,
            'total_remaining_semesters': len(semester_plans)
        }

    def _create_optimized_natural_sciences_plan(self, student, division_info, available_courses, completed_course_ids, max_credits):
        """إنشاء خطة محسنة للعلوم الطبيعية"""
        current_semester = student.Semester
        
        # تحديد المرحلة الحالية
        if current_semester <= 2:
            stage = 'عام'
        elif current_semester <= 4:
            stage = 'تشعيب متوسط'
        else:
            stage = 'تخصص نهائي'
        
        # تصفية المقررات - معالجة سريعة
        available_courses_filtered = [
            course for course in available_courses 
            if course['course_id'] not in completed_course_ids
        ]
        
        # إنشاء خطة الترمات
        semester_plans = self._create_fast_semester_plans(
            student, stage, current_semester, available_courses_filtered, max_credits
        )
        
        return {
            'message': 'تم إنشاء الخطة الأكاديمية بنجاح',
            'status': 'success',
            'student_info': {
                'name': student.Name,
                'student_id': student.Id,
                'current_semester': current_semester,
                'division': division_info['division_name'],
                'current_stage': stage,
                'max_credits_per_semester': max_credits
            },
            'semester_plans': semester_plans,
            'total_remaining_semesters': len(semester_plans)
        }

    def _create_fast_semester_plans(self, student, stage, current_semester, available_courses, max_credits):
        """إنشاء خطط الترمات بشكل سريع"""
        semester_plans = {}
        
        # حساب عدد الترمات المتبقية
        max_semesters = 8
        remaining_semesters = max_semesters - current_semester
        
        # توزيع المقررات على الترمات - خوارزمية محسنة
        courses_per_semester = self._distribute_courses_optimized(
            available_courses, remaining_semesters, max_credits
        )
        
        for i in range(remaining_semesters):
            semester_number = current_semester + i + 1
            if semester_number > max_semesters:
                break
                
            semester_key = f'semester_{semester_number}'
            courses = courses_per_semester.get(i, [])
            
            semester_plans[semester_key] = {
                'semester_number': semester_number,
                'semester_name': f'الترم {semester_number}',
                'stage': stage,
                'courses': courses,
                'total_credits': sum(course.get('credits', 0) for course in courses),
                'note': f'مقررات مرحلة {stage}'
            }
        
        return semester_plans

    def _distribute_courses_optimized(self, available_courses, remaining_semesters, max_credits):
        """توزيع المقررات على الترمات بطريقة محسنة"""
        if not available_courses or remaining_semesters <= 0:
            return {}
        
        # ترتيب المقررات حسب الأولوية - معالجة سريعة
        sorted_courses = sorted(
            available_courses,
            key=lambda x: (not x.get('is_mandatory', False), x.get('semester', 99), x.get('credits', 0))
        )
        
        semester_plans = {}
        course_index = 0
        
        for semester_idx in range(remaining_semesters):
            current_credits = 0
            semester_courses = []
            
            # إضافة المقررات للترم الحالي
            while course_index < len(sorted_courses) and current_credits < max_credits:
                course = sorted_courses[course_index]
                course_credits = course.get('credits', 0)
                
                if current_credits + course_credits <= max_credits:
                    semester_courses.append({
                        'course_id': course['course_id'],
                        'course_name': course['name'],
                        'course_code': course['code'],
                        'credits': course_credits
                    })
                    current_credits += course_credits
                    course_index += 1
                else:
                    break
            
            semester_plans[semester_idx] = semester_courses
            
            # إذا انتهت المقررات، توقف
            if course_index >= len(sorted_courses):
                break
        
        return semester_plans

    def _get_division_info(self, student):
        """الحصول على معلومات الشعبة"""
        division_name = student.division.Name
        return self.specialization_system.get(division_name)

    def _create_biology_geology_plan(self, student, division_info):
        """إنشاء خطة للمسارات البيولوجية والجيولوجية"""
        current_semester = student.Semester
        student_gpa = self._calculate_student_gpa(student)
        max_credits = self._get_max_credits(student_gpa)
        
        plan = {
            'student_info': self._get_basic_student_info(student),
            'current_gpa': student_gpa,
            'max_credits_per_semester': max_credits,
            'track_type': division_info['type'],
            'current_stage': self._determine_current_stage_biology_geology(current_semester),
            'plan': {}
        }
        
        if current_semester <= 4:
            # من الترم 1 إلى 4 - شعبة عامة
            plan['plan'] = self._create_general_semesters_plan(student, current_semester, max_credits)
            
            # اقتراح التخصص في نهاية الترم 4
            if current_semester == 4:
                performance_analysis = self._analyze_student_performance(student)
                specialization_recommendation = self._recommend_specialization(
                    student, division_info['available_specializations'], performance_analysis
                )
                plan['specialization_recommendation'] = specialization_recommendation
            else:
                plan['specialization_recommendation'] = None
            
        else:
            # من الترم 5 إلى 8 - متخصص
            plan['plan'] = self._create_specialized_plan(student, current_semester, max_credits)
            plan['specialization_recommendation'] = None
            
        return plan

    def _create_natural_sciences_plan(self, student, division_info):
        """إنشاء خطة لمسار العلوم الطبيعية"""
        current_semester = student.Semester
        student_gpa = self._calculate_student_gpa(student)
        max_credits = self._get_max_credits(student_gpa)
        
        plan = {
            'student_info': self._get_basic_student_info(student),
            'current_gpa': student_gpa,
            'max_credits_per_semester': max_credits,
            'track_type': division_info['type'],
            'current_stage': self._determine_current_stage_natural_sciences(current_semester),
            'plan': {}
        }
        
        if current_semester <= 2:
            # السنة الأولى - شعبة عامة
            if current_semester == 1:
                plan['plan'] = self._create_semester_plan_until(student, 2, max_credits)
            else:  # semester 2
                intermediate_recommendation = self._recommend_intermediate_specialization(student)
                plan['intermediate_specialization_recommendation'] = intermediate_recommendation
                plan['plan'] = self._create_intermediate_specialization_plans(
                    student, division_info['intermediate_specializations'], current_semester, max_credits
                )
                
        elif current_semester <= 4:
            # السنة الثانية - تشعيب متوسط
            if current_semester == 3:
                plan['plan'] = self._create_semester_plan_until(student, 4, max_credits)
            else:  # semester 4
                final_recommendation = self._recommend_final_specialization(student, division_info['final_specializations'], current_semester, max_credits)
                plan['final_specialization_recommendation'] = final_recommendation
                plan['plan'] = self._create_final_specialization_plans(
                    student, division_info['final_specializations'], current_semester, max_credits
                )
                
        else:
            # السنة الثالثة والرابعة - تخصص نهائي
            plan['plan'] = self._create_specialized_plan(student, current_semester, max_credits)
            
        return plan

    def _create_intermediate_specialized_plan(self, student, division_info):
        """إنشاء خطة للطلاب في التشعيب المتوسط (الرياضيات والفيزياء، الكيمياء والفيزياء)"""
        current_semester = student.Semester
        student_gpa = self._calculate_student_gpa(student)
        max_credits = self._get_max_credits(student_gpa)
        
        plan = {
            'student_info': self._get_basic_student_info(student),
            'current_gpa': student_gpa,
            'max_credits_per_semester': max_credits,
            'track_type': division_info['type'],
            'current_stage': f'التشعيب المتوسط - {student.division.Name}',
            'plan': {}
        }
        
        # إنشاء خطة للفصول المتبقية في التشعيب المتوسط
        remaining_semesters = []
        if current_semester == 3:
            remaining_semesters = [4, 5]  # باقي التشعيب المتوسط + أول ترم تخصص نهائي
        elif current_semester == 4:
            remaining_semesters = [5]  # انتقال للتخصص النهائي
            # إضافة توصية للتخصص النهائي
            final_recommendation = self._recommend_final_specialization(student, division_info['final_specializations'], current_semester, max_credits)
            plan['final_specialization_recommendation'] = final_recommendation
        
        for semester in remaining_semesters:
            if semester <= 4:
                # فصول التشعيب المتوسط
                semester_courses = self._get_specialization_courses(
                    student, student.division.Name, semester, max_credits
                )
                plan[f'semester_{semester}'] = {
                    'semester_number': semester,
                    'semester_name': f'الترم {semester} - {student.division.Name}',
                    'courses': semester_courses,
                    'total_credits': sum(course['credits'] for course in semester_courses)
                }
            else:
                # الترم الأول للتخصص النهائي
                plan[f'semester_{semester}'] = {
                    'semester_number': semester,
                    'semester_name': f'الترم {semester} - تخصص نهائي',
                    'courses': [],
                    'note': 'يتطلب اختيار التخصص النهائي أولاً'
                }
                
        return plan

    def _create_final_specialized_plan(self, student, division_info):
        """إنشاء خطة للطلاب في التخصص النهائي"""
        current_semester = student.Semester
        student_gpa = self._calculate_student_gpa(student)
        max_credits = self._get_max_credits(student_gpa)
        
        plan = {
            'student_info': self._get_basic_student_info(student),
            'current_gpa': student_gpa,
            'max_credits_per_semester': max_credits,
            'track_type': division_info['type'],
            'current_stage': f'التخصص النهائي - {student.division.Name}',
            'plan': {}
        }
        
        # إنشاء خطة للفصول المتبقية حتى التخرج
        for semester in range(current_semester + 1, 9):  # حتى الترم 8
            semester_courses = self._get_specialization_courses(
                student, student.division.Name, semester, max_credits
            )
            plan[f'semester_{semester}'] = {
                'semester_number': semester,
                'semester_name': f'الترم {semester} - {student.division.Name}',
                'courses': semester_courses,
                'total_credits': sum(course['credits'] for course in semester_courses),
                'specialization': student.division.Name
            }
            
        return plan

    def _calculate_student_gpa(self, student):
        """حساب متوسط GPA الطالب من حقول GPA1-GPA8 في جدول Students"""
        try:
            # جمع جميع قيم GPA التي ليست null
            gpa_values = []
            
            # فحص كل حقل GPA من GPA1 إلى GPA8
            for gpa_field in ['GPA1', 'GPA2', 'GPA3', 'GPA4', 'GPA5', 'GPA6', 'GPA7', 'GPA8']:
                gpa_value = getattr(student, gpa_field, None)
                if gpa_value is not None:
                    gpa_values.append(float(gpa_value))
            
            # حساب المتوسط إذا كان هناك قيم
            if gpa_values:
                average_gpa = sum(gpa_values) / len(gpa_values)
                return round(average_gpa, 2)
            else:
                return 0.0
            
        except Exception as e:
            print(f"خطأ في حساب GPA للطالب {student.Id}: {e}")
            return 0.0

    def _get_max_credits(self, gpa):
        """تحديد الحد الأقصى للساعات بناءً على GPA"""
        if gpa < 2.0:
            return 10
        else:
            return 18

    def _get_basic_student_info(self, student):
        """معلومات الطالب الأساسية"""
        return {
            'id': student.Id,
            'name': student.Name,
            'current_semester': student.Semester,
            'division': student.division.Name,
            'credits_completed': student.CreditsCompleted or 0
        }

    def _determine_current_stage_biology_geology(self, semester):
        """تحديد المرحلة الحالية للمسارات البيولوجية والجيولوجية"""
        if semester <= 4:
            return 'السنة الأولى والثانية - شعبة عامة (ترم 1-4)'
        else:
            return 'السنة الثالثة والرابعة - متخصص (ترم 5-8)'

    def _determine_current_stage_natural_sciences(self, semester):
        """تحديد المرحلة الحالية لمسار العلوم الطبيعية"""
        if semester <= 2:
            return 'السنة الأولى - شعبة عامة'
        elif semester <= 4:
            return 'السنة الثانية - تشعيب متوسط'
        else:
            return 'السنة الثالثة والرابعة - تخصص نهائي'

    def _create_general_semesters_plan(self, student, current_semester, max_credits):
        """إنشاء خطة للفصول العامة"""
        plan = {}
        
        # تحديد الفصول المتبقية في المرحلة العامة
        remaining_semesters = []
        if current_semester == 1:
            remaining_semesters = [2, 3, 4]
        elif current_semester == 2:
            remaining_semesters = [3, 4]
        elif current_semester == 3:
            remaining_semesters = [4]
        elif current_semester == 4:
            # إذا كان في الترم 4، نعرض فقط خطة الترم التالي (5) كمتخصص
            remaining_semesters = [5]
            
        for semester in remaining_semesters:
            if semester <= 4:
                # فصول عامة
                semester_courses = self._get_general_courses_for_semester(
                    student, semester, max_credits
                )
                plan[f'semester_{semester}'] = {
                    'semester_number': semester,
                    'semester_name': f'الترم {semester} - عام',
                    'courses': semester_courses,
                    'total_credits': sum(course['credits'] for course in semester_courses),
                    'course_ratio': self._calculate_course_ratio(semester_courses)
                }
            else:
                # فصول متخصصة (الترم 5 فما فوق)
                semester_courses = self._get_specialization_courses(
                    student, 'متخصص', semester, max_credits
                )
                plan[f'semester_{semester}'] = {
                    'semester_number': semester,
                    'semester_name': f'الترم {semester} - متخصص',
                    'courses': semester_courses,
                    'total_credits': sum(course['credits'] for course in semester_courses),
                    'note': 'يتطلب اختيار التخصص أولاً'
                }
            
        return plan

    def _create_semester_plan_until(self, student, end_semester, max_credits):
        """إنشاء خطة من الترم الحالي حتى ترم معين"""
        plan = {}
        current_semester = student.Semester
        
        for semester in range(current_semester + 1, end_semester + 1):
            semester_courses = self._get_courses_for_semester(
                student, semester, max_credits
            )
            plan[f'semester_{semester}'] = {
                'semester_number': semester,
                'semester_name': f'الترم {semester}',
                'courses': semester_courses,
                'total_credits': sum(course['credits'] for course in semester_courses),
                'course_ratio': self._calculate_course_ratio(semester_courses)
            }
            
        return plan

    def _get_general_courses_for_semester(self, student, semester, max_credits):
        """الحصول على المقررات العامة لترم معين مع البيانات الكاملة"""
        from models import Courses
        
        # الحصول على المقررات المتاحة للشعبة
        available_courses = self._get_available_courses_for_division(student.DivisionId)
        
        # تصفية المقررات حسب الترم ومتطلبات الطالب
        completed_courses = self._get_completed_course_ids(student.Id)
        
        # اختيار المقررات بنسبة 3:1 (إجباري:اختياري)
        mandatory_courses = [c for c in available_courses if c['is_mandatory'] and c['course_id'] not in completed_courses]
        elective_courses = [c for c in available_courses if not c['is_mandatory'] and c['course_id'] not in completed_courses]
        
        selected_courses = []
        total_credits = 0
        
        # إضافة المقررات الإجبارية أولاً
        for course_data in mandatory_courses:
            if total_credits + course_data['credits'] <= max_credits:
                # الحصول على بيانات المقرر الكاملة من قاعدة البيانات
                course = Courses.query.get(course_data['course_id'])
                if course:
                    selected_courses.append({
                        'course_id': course.Id,
                        'course_name': course.Name,
                        'course_code': course.Code,
                        'credits': course.Credits
                    })
                    total_credits += course.Credits
                
        # إضافة بعض المقررات الاختيارية
        remaining_credits = max_credits - total_credits
        for course_data in elective_courses:
            if total_credits + course_data['credits'] <= max_credits and len([c for c in selected_courses if not course_data['is_mandatory']]) < len(selected_courses) // 3:
                course = Courses.query.get(course_data['course_id'])
                if course:
                    selected_courses.append({
                        'course_id': course.Id,
                        'course_name': course.Name,
                        'course_code': course.Code,
                        'credits': course.Credits
                    })
                    total_credits += course.Credits
                
        return selected_courses[:6]  # حد أقصى 6 مقررات

    def _get_courses_for_semester(self, student, semester, max_credits):
        """الحصول على المقررات لترم معين"""
        return self._get_general_courses_for_semester(student, semester, max_credits)

    def _analyze_student_performance(self, student):
        """تحليل أداء الطالب مع تحليل شامل للدرجات من جدول Enrollments - محسن للسرعة"""
        # التحقق من الكاش أولاً
        cache_key = f"performance_{student.Id}_{student.Semester}"
        if cache_key in self._performance_cache:
            return self._performance_cache[cache_key]
            
        from models import Enrollments
        
        # استعلام محسن واحد بدلاً من عدة استعلامات
        enrollments = Enrollments.query.filter_by(
            StudentId=student.Id,
            IsCompleted='مكتملة'
        ).join(Enrollments.course).join(Courses.department).all()
        
        performance = {
            'math_performance': [],
            'physics_performance': [],
            'chemistry_performance': [],
            'biology_performance': [],
            'geology_performance': [],
            'computer_science_performance': [],
            'overall_gpa': self._calculate_student_gpa(student),
            'detailed_grades': [],  # تفاصيل جميع الدرجات
            'exam_performance': {   # تحليل أداء الامتحانات
                'exam1_average': 0,
                'exam2_average': 0,
                'final_average': 0,
                'total_courses': 0
            }
        }
        
        # متغيرات لحساب متوسط الامتحانات
        exam1_total = 0
        exam2_total = 0
        final_total = 0
        courses_count = 0
        
        # تحليل الدرجات حسب أقسام الكورسات - معالجة محسنة
        for enrollment in enrollments:
            if enrollment.Grade is not None:
                course = enrollment.course
                department_name = course.department.Name.lower()
                course_name = course.Name.lower()
                
                # جمع جميع الدرجات
                exam1 = float(enrollment.Exam1Grade) if enrollment.Exam1Grade else 0
                exam2 = float(enrollment.Exam2Grade) if enrollment.Exam2Grade else 0
                final_grade = float(enrollment.Grade) if enrollment.Grade else 0
                total_150 = exam1 + exam2 + final_grade
                
                # تحويل إلى مقياس 4.0 (من 150 إلى 4.0)
                grade_4_scale = (total_150 / 150) * 4.0 if total_150 > 0 else 0
                
                # حفظ تفاصيل الدرجات
                performance['detailed_grades'].append({
                    'course_name': course.Name,
                    'course_code': course.Code,
                    'department': course.department.Name,
                    'semester': enrollment.NumberOFSemster,
                    'exam1_grade': exam1,
                    'exam1_percentage': (exam1 / 30) * 100 if exam1 > 0 else 0,
                    'exam2_grade': exam2,
                    'exam2_percentage': (exam2 / 30) * 100 if exam2 > 0 else 0,
                    'final_grade': final_grade,
                    'final_percentage': (final_grade / 90) * 100 if final_grade > 0 else 0,
                    'total_150': total_150,
                    'total_percentage': (total_150 / 150) * 100 if total_150 > 0 else 0,
                    'gpa_4_scale': round(grade_4_scale, 2)
                })
                
                # حساب متوسطات الامتحانات
                if exam1 > 0:
                    exam1_total += exam1
                if exam2 > 0:
                    exam2_total += exam2
                if final_grade > 0:
                    final_total += final_grade
                courses_count += 1
                
                # تصنيف المواد حسب القسم - استخدام كاش
                subject_type = self._determine_subject_type_cached(department_name, course_name)
                
                if subject_type == 'math':
                    performance['math_performance'].append(grade_4_scale)
                elif subject_type == 'physics':
                    performance['physics_performance'].append(grade_4_scale)
                elif subject_type == 'chemistry':
                    performance['chemistry_performance'].append(grade_4_scale)
                elif subject_type == 'biology':
                    performance['biology_performance'].append(grade_4_scale)
                elif subject_type == 'geology':
                    performance['geology_performance'].append(grade_4_scale)
                elif subject_type == 'computer_science':
                    performance['computer_science_performance'].append(grade_4_scale)
        
        # حساب متوسطات الامتحانات
        if courses_count > 0:
            performance['exam_performance'] = {
                'exam1_average': round(exam1_total / courses_count, 2),
                'exam1_percentage': round((exam1_total / courses_count / 30) * 100, 2),
                'exam2_average': round(exam2_total / courses_count, 2),
                'exam2_percentage': round((exam2_total / courses_count / 30) * 100, 2),
                'final_average': round(final_total / courses_count, 2),
                'final_percentage': round((final_total / courses_count / 90) * 100, 2),
                'total_courses': courses_count
            }
        
        # حساب المتوسطات على مقياس 4.0 لكل مادة
        for subject in ['math_performance', 'physics_performance', 'chemistry_performance', 
                       'biology_performance', 'geology_performance', 'computer_science_performance']:
            if performance[subject]:
                performance[f'{subject}_avg'] = round(sum(performance[subject]) / len(performance[subject]), 2)
                performance[f'{subject}_count'] = len(performance[subject])
            else:
                performance[f'{subject}_avg'] = 0.0
                performance[f'{subject}_count'] = 0
        
        # حفظ في الكاش
        self._performance_cache[cache_key] = performance
        return performance

    @lru_cache(maxsize=500)
    def _determine_subject_type_cached(self, department_name, course_name):
        """نسخة محسنة من تحديد نوع المادة مع كاش"""
        return self._determine_subject_type(department_name, course_name)

    def _determine_subject_type(self, department_name, course_name):
        """تحديد نوع المادة بناءً على اسم القسم واسم المقرر"""
        
        # أولاً: التصنيف حسب أسماء الأقسام (الأولوية الأولى)
        department_mappings = {
            'رياضيات': 'math',
            'mathematics': 'math',
            'math': 'math',
            'الرياضيات': 'math',
            
            'فيزياء': 'physics', 
            'physics': 'physics',
            'الفيزياء': 'physics',
            
            'كيمياء': 'chemistry',
            'chemistry': 'chemistry',
            'الكيمياء': 'chemistry',
            'كيمياء حيوية': 'chemistry',
            'biochemistry': 'chemistry',
            
            'أحياء': 'biology',
            'biology': 'biology',
            'الأحياء': 'biology',
            'علم الحيوان': 'biology',
            'zoology': 'biology',
            'علم النبات': 'biology', 
            'botany': 'biology',
            'نبات': 'biology',
            'حيوان': 'biology',
            
            'جيولوجيا': 'geology',
            'geology': 'geology',
            'الجيولوجيا': 'geology',
            'علوم الأرض': 'geology',
            'earth sciences': 'geology',
            
            'حاسب': 'computer_science',
            'computer': 'computer_science',
            'علوم الحاسب': 'computer_science',
            'computer science': 'computer_science',
            'حاسوب': 'computer_science'
        }
        
        # التحقق من اسم القسم أولاً
        for dept_keyword, subject_type in department_mappings.items():
            if dept_keyword in department_name:
                return subject_type
        
        # ثانياً: التصنيف حسب أسماء المقررات (كدعم إضافي)
        course_mappings = {
            'math': ['رياض', 'math', 'calculus', 'algebra', 'geometry', 'statistics', 'إحصاء', 'جبر', 'هندسة', 'تفاضل', 'تكامل'],
            'physics': ['فيزياء', 'physics', 'mechanics', 'thermodynamics', 'optics', 'ميكانيكا', 'بصريات', 'حرارة'],
            'chemistry': ['كيمياء', 'chemistry', 'organic', 'inorganic', 'analytical', 'عضوية', 'غير عضوية', 'تحليلية'],
            'biology': ['أحياء', 'biology', 'حيوان', 'نبات', 'zoology', 'botany', 'anatomy', 'physiology', 'تشريح', 'وظائف'],
            'geology': ['جيولوج', 'geology', 'minerals', 'rocks', 'معادن', 'صخور', 'أرض'],
            'computer_science': ['حاسب', 'computer', 'programming', 'software', 'algorithm', 'برمجة', 'خوارزميات', 'نظم']
        }
        
        for subject_type, keywords in course_mappings.items():
            for keyword in keywords:
                if keyword in course_name:
                    return subject_type
        
        # إذا لم يتم العثور على تصنيف، إرجاع None
        return None
        
    def _get_department_based_courses(self, student):
        """الحصول على الكورسات مصنفة حسب الأقسام للطالب"""
        enrollments = Enrollments.query.filter_by(
            StudentId=student.Id,
            IsCompleted='مكتملة'
        ).all()
        
        department_courses = {}
        
        for enrollment in enrollments:
            if enrollment.Grade is not None:
                course = enrollment.course
                department_name = course.department.Name
                
                if department_name not in department_courses:
                    department_courses[department_name] = []
                
                department_courses[department_name].append({
                    'course_name': course.Name,
                    'course_code': course.Code,
                    'credits': course.Credits,
                    'grade': float(enrollment.Grade),
                    'semester': enrollment.NumberOFSemster
                })
        
        return department_courses

    def _recommend_specialization(self, student, available_specializations, performance):
        """اقتراح التخصص بناءً على الأداء"""
        recommendations = []
        
        for specialization in available_specializations:
            score = self._calculate_specialization_score(specialization, performance)
            recommendations.append({
                'specialization': specialization,
                'suitability_score': score,
                'recommendation_level': self._get_recommendation_level(score),
                'reasoning': self._get_specialization_reasoning(specialization, performance)
            })
        
        # ترتيب التوصيات حسب النقاط
        recommendations.sort(key=lambda x: x['suitability_score'], reverse=True)
        
        return {
            'recommended_specialization': recommendations[0],
            'all_recommendations': recommendations,
            'performance_summary': self._summarize_performance(performance)
        }

    def _calculate_specialization_score(self, specialization, performance):
        """حساب نقاط الملاءمة للتخصص بناءً على الأداء الفعلي في الأقسام"""
        score = 0
        base_gpa = performance['overall_gpa']
        
        if 'حيوان' in specialization:
            # تخصص علم الحيوان
            biology_avg = performance['biology_performance_avg']
            chemistry_avg = performance['chemistry_performance_avg']
            
            score += biology_avg * 0.6  # أداء الأحياء أولوية قصوى
            score += chemistry_avg * 0.3  # الكيمياء مهمة كدعم
            score += base_gpa * 0.1  # المعدل العام
            
        elif 'نبات' in specialization:
            # تخصص النبات والكيمياء
            biology_avg = performance['biology_performance_avg']
            chemistry_avg = performance['chemistry_performance_avg']
            
            score += biology_avg * 0.5  # أداء الأحياء
            score += chemistry_avg * 0.4  # الكيمياء أساسية
            score += base_gpa * 0.1
            
        elif 'كيمياء' in specialization and 'حيوية' in specialization:
            # تخصص الكيمياء الحيوية
            chemistry_avg = performance['chemistry_performance_avg']
            biology_avg = performance['biology_performance_avg']
            
            score += chemistry_avg * 0.6  # الكيمياء أساسية
            score += biology_avg * 0.3   # الأحياء مساندة
            score += base_gpa * 0.1
            
        elif 'كيمياء' in specialization:
            # تخصص الكيمياء العامة
            chemistry_avg = performance['chemistry_performance_avg']
            math_avg = performance['math_performance_avg']
            physics_avg = performance['physics_performance_avg']
            
            score += chemistry_avg * 0.7  # الكيمياء أساسية
            score += math_avg * 0.15      # الرياضيات مساندة
            score += physics_avg * 0.05   # الفيزياء مساندة
            score += base_gpa * 0.1
            
        elif 'جيولوج' in specialization:
            # تخصص الجيولوجيا والكيمياء
            geology_avg = performance['geology_performance_avg']
            chemistry_avg = performance['chemistry_performance_avg']
            physics_avg = performance['physics_performance_avg']
            
            score += geology_avg * 0.6    # الجيولوجيا أساسية
            score += chemistry_avg * 0.2  # الكيمياء مساندة
            score += physics_avg * 0.1    # الفيزياء مساندة
            score += base_gpa * 0.1
            
        elif 'رياضيات' in specialization and 'حاسب' in specialization:
            # تخصص الرياضيات وعلوم الحاسب
            math_avg = performance['math_performance_avg']
            cs_avg = performance['computer_science_performance_avg']
            physics_avg = performance['physics_performance_avg']
            
            score += math_avg * 0.5       # الرياضيات أساسية
            score += cs_avg * 0.3         # علوم الحاسب مهمة
            score += physics_avg * 0.1    # الفيزياء مساندة
            score += base_gpa * 0.1
            
        elif 'رياضيات' in specialization:
            # تخصص الرياضيات
            math_avg = performance['math_performance_avg']
            physics_avg = performance['physics_performance_avg']
            
            score += math_avg * 0.7       # الرياضيات أساسية
            score += physics_avg * 0.2    # الفيزياء مساندة
            score += base_gpa * 0.1
            
        elif 'فيزياء' in specialization:
            # تخصص الفيزياء
            physics_avg = performance['physics_performance_avg']
            math_avg = performance['math_performance_avg']
            
            score += physics_avg * 0.7    # الفيزياء أساسية
            score += math_avg * 0.2       # الرياضيات مساندة
            score += base_gpa * 0.1
            
        else:
            # تخصص غير معروف - استخدام المعدل العام فقط
            score = base_gpa
            
        return round(score, 2)

    def _get_recommendation_level(self, score):
        """تحديد مستوى التوصية"""
        if score >= 3.5:
            return 'ممتاز'
        elif score >= 3.0:
            return 'جيد جداً'
        elif score >= 2.5:
            return 'جيد'
        elif score >= 2.0:
            return 'مقبول'
        else:
            return 'ضعيف'

    def _get_specialization_reasoning(self, specialization, performance):
        """تفسير سبب التوصية بناءً على الأداء الفعلي في الأقسام"""
        reasons = []
        
        # الحصول على متوسطات الأداء
        biology_avg = performance['biology_performance_avg']
        chemistry_avg = performance['chemistry_performance_avg']
        math_avg = performance['math_performance_avg']
        physics_avg = performance['physics_performance_avg']
        geology_avg = performance['geology_performance_avg']
        cs_avg = performance['computer_science_performance_avg']
        overall_gpa = performance['overall_gpa']
        
        if 'حيوان' in specialization:
            if biology_avg >= 3.5:
                reasons.append(f'أداء ممتاز في مقررات الأحياء (متوسط: {biology_avg})')
            elif biology_avg >= 3.0:
                reasons.append(f'أداء جيد جداً في مقررات الأحياء (متوسط: {biology_avg})')
            elif biology_avg >= 2.5:
                reasons.append(f'أداء جيد في مقررات الأحياء (متوسط: {biology_avg})')
            
            if chemistry_avg >= 3.0:
                reasons.append(f'أداء قوي في الكيمياء يدعم التخصص (متوسط: {chemistry_avg})')
            elif chemistry_avg >= 2.5:
                reasons.append(f'أداء مقبول في الكيمياء (متوسط: {chemistry_avg})')
                
        elif 'نبات' in specialization:
            if biology_avg >= 3.0:
                reasons.append(f'أداء ممتاز في علوم النبات والأحياء (متوسط: {biology_avg})')
            
            if chemistry_avg >= 3.0:
                reasons.append(f'أداء قوي في الكيمياء المطلوبة للتخصص (متوسط: {chemistry_avg})')
            
        elif 'كيمياء' in specialization:
            if chemistry_avg >= 3.5:
                reasons.append(f'أداء ممتاز في مقررات الكيمياء (متوسط: {chemistry_avg})')
            elif chemistry_avg >= 3.0:
                reasons.append(f'أداء جيد جداً في مقررات الكيمياء (متوسط: {chemistry_avg})')
            elif chemistry_avg >= 2.5:
                reasons.append(f'أداء جيد في مقررات الكيمياء (متوسط: {chemistry_avg})')
            
            if 'حيوية' in specialization and biology_avg >= 2.5:
                reasons.append(f'أداء جيد في الأحياء يدعم الكيمياء الحيوية (متوسط: {biology_avg})')
            
            if math_avg >= 3.0:
                reasons.append(f'أداء قوي في الرياضيات يدعم الكيمياء (متوسط: {math_avg})')
                
        elif 'جيولوج' in specialization:
            if geology_avg >= 3.0:
                reasons.append(f'أداء ممتاز في مقررات الجيولوجيا (متوسط: {geology_avg})')
            elif geology_avg > 0:
                reasons.append(f'أداء في مقررات الجيولوجيا (متوسط: {geology_avg})')
            
            if chemistry_avg >= 2.5:
                reasons.append(f'أداء جيد في الكيمياء المساندة (متوسط: {chemistry_avg})')
                
        elif 'رياضيات' in specialization:
            if math_avg >= 3.5:
                reasons.append(f'أداء ممتاز في مقررات الرياضيات (متوسط: {math_avg})')
            elif math_avg >= 3.0:
                reasons.append(f'أداء جيد جداً في مقررات الرياضيات (متوسط: {math_avg})')
            elif math_avg >= 2.5:
                reasons.append(f'أداء جيد في مقررات الرياضيات (متوسط: {math_avg})')
            
            if 'حاسب' in specialization:
                if cs_avg >= 3.0:
                    reasons.append(f'أداء قوي في علوم الحاسب (متوسط: {cs_avg})')
                elif cs_avg > 0:
                    reasons.append(f'خبرة في علوم الحاسب (متوسط: {cs_avg})')
                else:
                    reasons.append('إمكانية جيدة للتطور في علوم الحاسب')
            
            if physics_avg >= 2.5:
                reasons.append(f'أداء جيد في الفيزياء يدعم الرياضيات (متوسط: {physics_avg})')
                
        elif 'فيزياء' in specialization:
            if physics_avg >= 3.5:
                reasons.append(f'أداء ممتاز في مقررات الفيزياء (متوسط: {physics_avg})')
            elif physics_avg >= 3.0:
                reasons.append(f'أداء جيد جداً في مقررات الفيزياء (متوسط: {physics_avg})')
            elif physics_avg >= 2.5:
                reasons.append(f'أداء جيد في مقررات الفيزياء (متوسط: {physics_avg})')
            
            if math_avg >= 3.0:
                reasons.append(f'أداء قوي في الرياضيات يدعم الفيزياء (متوسط: {math_avg})')
        
        # إضافة معلومة عن المعدل العام إذا كان جيد
        if overall_gpa >= 3.5:
            reasons.append(f'معدل تراكمي ممتاز ({overall_gpa})')
        elif overall_gpa >= 3.0:
            reasons.append(f'معدل تراكمي جيد جداً ({overall_gpa})')
        elif overall_gpa >= 2.5:
            reasons.append(f'معدل تراكمي جيد ({overall_gpa})')
        
        # إذا لم توجد أسباب واضحة
        if not reasons:
            reasons.append(f'بناءً على المعدل التراكمي العام ({overall_gpa})')
            if overall_gpa < 2.0:
                reasons.append('يُنصح بالتركيز على تحسين الأداء العام أولاً')
            
        return reasons

    def _summarize_performance(self, performance):
        """ملخص الأداء المحسن"""
        return {
            'overall_gpa': performance['overall_gpa'],
            'strongest_subject': self._get_strongest_subject(performance),
            'weakest_subject': self._get_weakest_subject(performance),
            'performance_trend': self._analyze_performance_trend(performance),
            'subjects_performance': self._get_detailed_subjects_performance(performance),
            'recommendations': self._get_performance_recommendations(performance)
        }

    def _get_strongest_subject(self, performance):
        """أقوى مادة للطالب"""
        subjects = {
            'الرياضيات': performance['math_performance_avg'],
            'الفيزياء': performance['physics_performance_avg'],
            'الكيمياء': performance['chemistry_performance_avg'],
            'الأحياء': performance['biology_performance_avg'],
            'الجيولوجيا': performance['geology_performance_avg'],
            'علوم الحاسب': performance['computer_science_performance_avg']
        }
        
        # تصفية المواد التي لها درجات
        subjects_with_grades = {k: v for k, v in subjects.items() if v > 0}
        
        if subjects_with_grades:
            strongest = max(subjects_with_grades, key=subjects_with_grades.get)
            strongest_avg = subjects_with_grades[strongest]
            return {
                'subject': strongest,
                'average': strongest_avg,
                'performance_level': self._get_performance_level(strongest_avg)
            }
        else:
            return {
                'subject': 'غير محدد',
                'average': 0.0,
                'performance_level': 'لا توجد بيانات'
            }

    def _get_weakest_subject(self, performance):
        """أضعف مادة للطالب"""
        subjects = {
            'الرياضيات': performance['math_performance_avg'],
            'الفيزياء': performance['physics_performance_avg'],
            'الكيمياء': performance['chemistry_performance_avg'],
            'الأحياء': performance['biology_performance_avg'],
            'الجيولوجيا': performance['geology_performance_avg'],
            'علوم الحاسب': performance['computer_science_performance_avg']
        }
        
        # تصفية المواد التي لها درجات
        subjects_with_grades = {k: v for k, v in subjects.items() if v > 0}
        
        if subjects_with_grades:
            weakest = min(subjects_with_grades, key=subjects_with_grades.get)
            weakest_avg = subjects_with_grades[weakest]
            return {
                'subject': weakest,
                'average': weakest_avg,
                'performance_level': self._get_performance_level(weakest_avg)
            }
        else:
            return {
                'subject': 'غير محدد',
                'average': 0.0,
                'performance_level': 'لا توجد بيانات'
            }

    def _get_performance_level(self, average):
        """تحديد مستوى الأداء"""
        if average >= 3.5:
            return 'ممتاز'
        elif average >= 3.0:
            return 'جيد جداً'
        elif average >= 2.5:
            return 'جيد'
        elif average >= 2.0:
            return 'مقبول'
        elif average > 0:
            return 'ضعيف'
        else:
            return 'لا توجد بيانات'

    def _get_detailed_subjects_performance(self, performance):
        """تفاصيل أداء جميع المواد"""
        subjects_details = {}
        
        subjects = {
            'الرياضيات': performance['math_performance_avg'],
            'الفيزياء': performance['physics_performance_avg'],
            'الكيمياء': performance['chemistry_performance_avg'],
            'الأحياء': performance['biology_performance_avg'],
            'الجيولوجيا': performance['geology_performance_avg'],
            'علوم الحاسب': performance['computer_science_performance_avg']
        }
        
        for subject, avg in subjects.items():
            if avg > 0:
                subjects_details[subject] = {
                    'average': avg,
                    'performance_level': self._get_performance_level(avg),
                    'courses_count': len(performance[f'{self._get_subject_key(subject)}_performance'])
                }
            
        return subjects_details

    def _get_subject_key(self, subject_name):
        """الحصول على مفتاح المادة في قاموس الأداء"""
        mapping = {
            'الرياضيات': 'math',
            'الفيزياء': 'physics',
            'الكيمياء': 'chemistry',
            'الأحياء': 'biology',
            'الجيولوجيا': 'geology',
            'علوم الحاسب': 'computer_science'
        }
        return mapping.get(subject_name, 'unknown')

    def _get_performance_recommendations(self, performance):
        """توصيات لتحسين الأداء"""
        recommendations = []
        overall_gpa = performance['overall_gpa']
        
        if overall_gpa < 2.0:
            recommendations.append('ضرورة التركيز على رفع المعدل التراكمي فوق 2.0 لتجنب الإنذار الأكاديمي')
            recommendations.append('طلب المساعدة الأكاديمية من الأساتذة والمرشدين')
        elif overall_gpa < 2.5:
            recommendations.append('العمل على تحسين المعدل التراكمي للحصول على فرص أفضل')
        
        # فحص أداء المواد الفردية
        weakest = self._get_weakest_subject(performance)
        if weakest['average'] > 0 and weakest['average'] < 2.5:
            recommendations.append(f'التركيز على تحسين الأداء في مادة {weakest["subject"]} (متوسط حالي: {weakest["average"]})')
        
        # اقتراحات للتخصص
        strongest = self._get_strongest_subject(performance)
        if strongest['average'] >= 3.0:
            recommendations.append(f'الاستفادة من القوة في مادة {strongest["subject"]} لاختيار التخصص المناسب')
        
        return recommendations

    def _analyze_performance_trend(self, performance):
        """تحليل اتجاه الأداء"""
        if performance['overall_gpa'] >= 3.5:
            return 'أداء ممتاز'
        elif performance['overall_gpa'] >= 3.0:
            return 'أداء جيد جداً'
        elif performance['overall_gpa'] >= 2.5:
            return 'أداء جيد'
        elif performance['overall_gpa'] >= 2.0:
            return 'أداء مقبول'
        else:
            return 'يحتاج تحسين'

    def _create_single_specialization_plan(self, student, specialization, start_semester, max_credits):
        """إنشاء خطة لتخصص واحد"""
        plan = {}
        
        for semester in range(start_semester + 1, 9):  # حتى الترم 8
            semester_courses = self._get_specialization_courses(
                student, specialization, semester, max_credits
            )
            plan[f'semester_{semester}'] = {
                'semester_number': semester,
                'semester_name': f'الترم {semester}',
                'specialization': specialization,
                'courses': semester_courses,
                'total_credits': sum(course['credits'] for course in semester_courses)
            }
            
        return plan

    def _create_specialized_plan(self, student, current_semester, max_credits):
        """إنشاء خطة للطالب المتخصص"""
        plan = {}
        current_specialization = student.division.Name
        
        for semester in range(current_semester + 1, 9):  # حتى الترم 8
            semester_courses = self._get_specialization_courses(
                student, current_specialization, semester, max_credits
            )
            plan[f'semester_{semester}'] = {
                'semester_number': semester,
                'semester_name': f'الترم {semester}',
                'courses': semester_courses,
                'total_credits': sum(course['credits'] for course in semester_courses)
            }
            
        return plan

    def _recommend_intermediate_specialization(self, student):
        """اقتراح التشعيب المتوسط لمسار العلوم الطبيعية"""
        performance = self._analyze_student_performance(student)
        intermediate_options = ['الرياضيات والفيزياء', 'الكيمياء والفيزياء']
        
        recommendations = []
        for option in intermediate_options:
            score = self._calculate_intermediate_score(option, performance)
            recommendations.append({
                'specialization': option,
                'suitability_score': score,
                'recommendation_level': self._get_recommendation_level(score)
            })
            
        recommendations.sort(key=lambda x: x['suitability_score'], reverse=True)
        
        return {
            'recommended': recommendations[0],
            'all_options': recommendations
        }

    def _calculate_intermediate_score(self, option, performance):
        """حساب نقاط التشعيب المتوسط"""
        if 'رياضيات' in option and 'فيزياء' in option:
            return (performance['math_performance_avg'] * 0.5 + 
                   performance['physics_performance_avg'] * 0.4 + 
                   performance['overall_gpa'] * 0.1)
        elif 'كيمياء' in option and 'فيزياء' in option:
            return (performance['chemistry_performance_avg'] * 0.5 + 
                   performance['physics_performance_avg'] * 0.4 + 
                   performance['overall_gpa'] * 0.1)
        return performance['overall_gpa']

    def _recommend_final_specialization(self, student, current_specialization, options, performance):
        """التوصية بالتخصص النهائي مع تحليل معمق"""
        recommendations = []
        
        for option in options:
            # حساب نقاط الملاءمة
            suitability_score = self._calculate_final_score(option, performance)
            
            # التحليل المفصل
            detailed_analysis = self._get_detailed_specialization_analysis(option, performance)
            
            # تحديد مستوى التوصية
            confidence_level = "عالي" if suitability_score >= 3.5 else "متوسط" if suitability_score >= 3.0 else "منخفض"
            
            # الأسباب الرئيسية
            key_reasons = []
            if detailed_analysis['strengths']:
                key_reasons.extend(detailed_analysis['strengths'][:2])  # أقوى نقطتين
            if detailed_analysis['concerns']:
                key_reasons.extend([f"⚠️ {concern}" for concern in detailed_analysis['concerns'][:1]])
            
            recommendation = {
                'specialization': option,
                'suitability_score': round(suitability_score, 2),
                'confidence_level': confidence_level,
                'key_reasons': key_reasons,
                'detailed_analysis': detailed_analysis,
                'recommendation_text': self._generate_recommendation_text(option, suitability_score, detailed_analysis)
            }
            
            recommendations.append(recommendation)
            
        # ترتيب التوصيات حسب النقاط
        recommendations.sort(key=lambda x: x['suitability_score'], reverse=True)
        
        # التوصية الذكية الرئيسية
        top_recommendation = recommendations[0] if recommendations else None
        
        # تحليل الأداء العام
        performance_summary = {
            'overall_gpa': performance['overall_gpa'],
            'strongest_subject': self._get_strongest_subject(performance),
            'weakest_subject': self._get_weakest_subject(performance),
            'academic_standing': self._get_academic_standing(performance['overall_gpa']),
            'improvement_areas': self._get_improvement_areas(performance)
        }
        
        return {
            'smart_recommendation': {
                'recommended_specialization': top_recommendation['specialization'] if top_recommendation else None,
                'confidence_level': top_recommendation['confidence_level'] if top_recommendation else 'منخفض',
                'reasoning': top_recommendation['recommendation_text'] if top_recommendation else 'لا توجد بيانات كافية للتوصية',
                'suitability_score': top_recommendation['suitability_score'] if top_recommendation else 0,
                'key_reasons': top_recommendation['key_reasons'] if top_recommendation else []
            },
            'performance_analysis': performance_summary,
            'all_options': recommendations,
            'alternative_options': recommendations[1:3] if len(recommendations) > 1 else []
        }

    def _generate_recommendation_text(self, specialization, score, analysis):
        """توليد نص التوصية"""
        if score >= 3.5:
            strength_text = " و ".join(analysis['strengths'][:2]) if analysis['strengths'] else "أداء جيد"
            return f"توصية قوية بـ{specialization} بناءً على {strength_text}. هذا التخصص يناسب قدراتك الأكاديمية بشكل ممتاز."
        elif score >= 3.0:
            return f"توصية جيدة بـ{specialization}. تظهر قدرات مناسبة لهذا التخصص مع بعض المجالات للتحسين."
        elif score >= 2.5:
            concern_text = analysis['concerns'][0] if analysis['concerns'] else "بعض التحديات"
            return f"يمكن النظر في {specialization} ولكن مع الانتباه إلى {concern_text}. ينصح بالعمل على تحسين الأداء."
        else:
            return f"لا ينصح بـ{specialization} في الوقت الحالي. يفضل التركيز على تحسين الأداء الأكاديمي أولاً."

    def _get_strongest_subject(self, performance):
        """أقوى مادة للطالب"""
        subjects = {
            'الرياضيات': performance['math_performance_avg'],
            'الفيزياء': performance['physics_performance_avg'],
            'الكيمياء': performance['chemistry_performance_avg'],
            'الأحياء': performance['biology_performance_avg'],
            'الجيولوجيا': performance['geology_performance_avg'],
            'علوم الحاسب': performance['computer_science_performance_avg']
        }
        
        # تصفية المواد التي لها درجات
        subjects_with_grades = {k: v for k, v in subjects.items() if v > 0}
        
        if subjects_with_grades:
            strongest = max(subjects_with_grades, key=subjects_with_grades.get)
            strongest_avg = subjects_with_grades[strongest]
            return {
                'subject': strongest,
                'average': strongest_avg,
                'performance_level': self._get_performance_level(strongest_avg)
            }
        else:
            return {
                'subject': 'غير محدد',
                'average': 0.0,
                'performance_level': 'لا توجد بيانات'
            }

    def _get_weakest_subject(self, performance):
        """أضعف مادة للطالب"""
        subjects = {
            'الرياضيات': performance['math_performance_avg'],
            'الفيزياء': performance['physics_performance_avg'],
            'الكيمياء': performance['chemistry_performance_avg'],
            'الأحياء': performance['biology_performance_avg'],
            'الجيولوجيا': performance['geology_performance_avg'],
            'علوم الحاسب': performance['computer_science_performance_avg']
        }
        
        # تصفية المواد التي لها درجات
        subjects_with_grades = {k: v for k, v in subjects.items() if v > 0}
        
        if subjects_with_grades:
            weakest = min(subjects_with_grades, key=subjects_with_grades.get)
            weakest_avg = subjects_with_grades[weakest]
            return {
                'subject': weakest,
                'average': weakest_avg,
                'performance_level': self._get_performance_level(weakest_avg)
            }
        else:
            return {
                'subject': 'غير محدد',
                'average': 0.0,
                'performance_level': 'لا توجد بيانات'
            }

    def _get_academic_standing(self, gpa):
        """تحديد المستوى الأكاديمي"""
        if gpa >= 3.75:
            return 'ممتاز'
        elif gpa >= 3.25:
            return 'جيد جداً'
        elif gpa >= 2.75:
            return 'جيد'
        elif gpa >= 2.0:
            return 'مقبول'
        else:
            return 'ضعيف'

    def _get_improvement_areas(self, performance):
        """تحديد مجالات التحسين"""
        areas = []
        
        if performance['math_performance_avg'] < 2.5:
            areas.append('الرياضيات')
        if performance['physics_performance_avg'] < 2.5:
            areas.append('الفيزياء')
        if performance['chemistry_performance_avg'] < 2.5:
            areas.append('الكيمياء')
        if performance['computer_science_performance_avg'] < 2.5 and performance['computer_science_performance_avg'] > 0:
            areas.append('علوم الحاسب')
            
        return areas if areas else ['لا توجد مجالات محددة للتحسين']

    def _get_valid_final_specializations(self, current_division):
        """الحصول على التخصصات النهائية المتاحة حسب التشعيب المتوسط الحالي"""
        
        # قواعد التشعيب الكاملة حسب النظام المطلوب
        division_rules = {
            # مسار العلوم الطبيعية - التشعيب المتوسط
            'الرياضيات والفيزياء': [
                'الرياضيات الخاصة',
                'الفيزياء الخاصة', 
                'الرياضيات وعلوم الحاسب'
            ],
            
            'الكيمياء والفيزياء': [
                'الكيمياء الخاصة'
            ]
        }
        
        return division_rules.get(current_division, [])

    def _calculate_final_score(self, option, performance):
        """حساب نقاط التخصص النهائي"""
        if 'رياضيات' in option:
            return (performance['math_performance_avg'] * 0.7 + 
                   performance['overall_gpa'] * 0.3)
        elif 'فيزياء' in option:
            return (performance['physics_performance_avg'] * 0.7 + 
                   performance['overall_gpa'] * 0.3)
        elif 'كيمياء' in option:
            return (performance['chemistry_performance_avg'] * 0.7 + 
                   performance['overall_gpa'] * 0.3)
        return performance['overall_gpa']

    def _get_detailed_specialization_analysis(self, specialization, performance):
        """تحليل مفصل لملاءمة التخصص للطالب"""
        analysis = {
            'strengths': [],
            'concerns': [],
            'requirements': [],
            'career_prospects': []
        }
        
        # تحليل حسب التخصص
        if 'رياضيات' in specialization:
            math_avg = performance['math_performance_avg']
            
            if math_avg >= 3.5:
                analysis['strengths'].append(f'أداء ممتاز في الرياضيات ({math_avg:.2f})')
            elif math_avg >= 3.0:
                analysis['strengths'].append(f'أداء جيد جداً في الرياضيات ({math_avg:.2f})')
            elif math_avg >= 2.5:
                analysis['strengths'].append(f'أداء جيد في الرياضيات ({math_avg:.2f})')
            else:
                analysis['concerns'].append(f'أداء ضعيف في الرياضيات ({math_avg:.2f})')
            
            analysis['requirements'] = [
                'التفوق في مقررات التحليل الرياضي المتقدم',
                'إتقان الجبر الخطي والمعادلات التفاضلية',
                'مهارات قوية في الإثبات الرياضي'
            ]
            
            if 'حاسب' in specialization:
                cs_avg = performance['computer_science_performance_avg']
                if cs_avg > 0:
                    analysis['strengths'].append(f'خبرة في علوم الحاسب ({cs_avg:.2f})')
                else:
                    analysis['concerns'].append('لا توجد خبرة واضحة في علوم الحاسب')
                    
                analysis['career_prospects'] = [
                    'مطور برمجيات',
                    'محلل بيانات',
                    'باحث في الذكاء الاصطناعي',
                    'مدرس رياضيات وحاسوب'
                ]
            else:
                analysis['career_prospects'] = [
                    'مدرس رياضيات',
                    'باحث أكاديمي',
                    'محلل إحصائي',
                    'أخصائي تطوير المناهج'
                ]
                
        elif 'فيزياء' in specialization:
            physics_avg = performance['physics_performance_avg']
            math_avg = performance['math_performance_avg']
            
            if physics_avg >= 3.0:
                analysis['strengths'].append(f'أداء قوي في الفيزياء ({physics_avg:.2f})')
            else:
                analysis['concerns'].append(f'أداء ضعيف في الفيزياء ({physics_avg:.2f})')
                
            if math_avg >= 3.0:
                analysis['strengths'].append(f'أساس رياضي قوي يدعم الفيزياء ({math_avg:.2f})')
            else:
                analysis['concerns'].append('الرياضيات ضرورية لفهم الفيزياء المتقدمة')
            
            analysis['requirements'] = [
                'فهم عميق للميكانيكا الكلاسيكية والكمية',
                'مهارات رياضية متقدمة',
                'قدرة على التجريب والقياس الدقيق'
            ]
            
            analysis['career_prospects'] = [
                'باحث في الفيزياء',
                'مدرس فيزياء',
                'عالم في مختبرات البحث',
                'مطور تقنيات علمية'
            ]
            
        elif 'كيمياء' in specialization:
            chemistry_avg = performance['chemistry_performance_avg']
            math_avg = performance['math_performance_avg']
            
            if chemistry_avg >= 3.0:
                analysis['strengths'].append(f'أداء قوي في الكيمياء ({chemistry_avg:.2f})')
            else:
                analysis['concerns'].append(f'أداء ضعيف في الكيمياء ({chemistry_avg:.2f})')
                
            if math_avg >= 2.5:
                analysis['strengths'].append('أساس رياضي مناسب للكيمياء')
            
            analysis['requirements'] = [
                'فهم عميق للكيمياء العضوية وغير العضوية',
                'مهارات مختبرية متقدمة',
                'فهم الكيمياء الفيزيائية والتحليلية'
            ]
            
            analysis['career_prospects'] = [
                'كيميائي في الصناعة',
                'باحث في المختبرات',
                'مدرس كيمياء',
                'محلل كيميائي'
            ]
        
        # تحليل المعدل العام
        overall_gpa = performance['overall_gpa']
        if overall_gpa >= 3.5:
            analysis['strengths'].append(f'معدل تراكمي ممتاز ({overall_gpa:.2f})')
        elif overall_gpa >= 3.0:
            analysis['strengths'].append(f'معدل تراكمي جيد جداً ({overall_gpa:.2f})')
        elif overall_gpa >= 2.5:
            analysis['strengths'].append(f'معدل تراكمي جيد ({overall_gpa:.2f})')
        else:
            analysis['concerns'].append(f'معدل تراكمي منخفض ({overall_gpa:.2f}) - يحتاج تحسين')
        
        return analysis

    def _create_intermediate_specialization_plans(self, student, options, current_semester, max_credits):
        """إنشاء خطط للتشعيبات المتوسطة"""
        plans = {}
        
        for option in options:
            plans[option] = self._create_single_specialization_plan(
                student, option, current_semester, max_credits
            )
            
        return plans

    def _create_final_specialization_plans(self, student, options, current_semester, max_credits):
        """إنشاء خطط للتخصصات النهائية"""
        plans = {}
        
        for option in options:
            plans[option] = self._create_single_specialization_plan(
                student, option, current_semester, max_credits
            )
            
        return plans

    def _get_available_courses_for_division(self, division_id):
        """الحصول على المقررات المتاحة للشعبة مع معلومات القسم - محسن"""
        return self._get_all_division_data_bulk(division_id)

    def _get_courses_by_department(self, department_name):
        """الحصول على جميع المقررات لقسم معين"""
        courses = Courses.query.join(Departments).filter(
            Departments.Name.like(f'%{department_name}%')
        ).all()
        
        course_list = []
        for course in courses:
            course_list.append({
                'course_id': course.Id,
                'name': course.Name,
                'code': course.Code,
                'credits': course.Credits,
                'semester': course.Semester,
                'description': course.Description,
                'department_name': course.department.Name
            })
            
        return course_list

    def _get_specialization_related_courses(self, student, specialization):
        """الحصول على المقررات المرتبطة بتخصص معين - محسن"""
        available_courses = self._get_available_courses_for_division(student.DivisionId)
        completed_courses = self._get_completed_course_ids(student.Id)
        
        # تصفية المقررات حسب التخصص - معالجة محسنة
        relevant_courses = []
        
        for course in available_courses:
            if course['course_id'] in completed_courses:
                continue
                
            # تحديد إذا كان المقرر متعلق بالتخصص
            is_relevant = self._is_course_relevant_to_specialization(course, specialization)
            
            if is_relevant:
                course['relevance_score'] = self._calculate_course_relevance_score(course, specialization)
                relevant_courses.append(course)
        
        # ترتيب المقررات حسب الأهمية
        relevant_courses.sort(key=lambda x: (x['is_mandatory'], x['relevance_score']), reverse=True)
        
        return relevant_courses

    def _is_course_relevant_to_specialization(self, course, specialization):
        """تحديد إذا كان المقرر متعلق بالتخصص"""
        course_subject = course['subject_type']
        department_name = course['department_name'].lower()
        course_name = course['name'].lower()
        
        if 'حيوان' in specialization:
            return course_subject == 'biology' or 'حيوان' in course_name or 'zoology' in course_name
        elif 'نبات' in specialization:
            return course_subject in ['biology', 'chemistry'] or 'نبات' in course_name or 'botany' in course_name
        elif 'كيمياء' in specialization:
            return course_subject == 'chemistry' or 'كيمياء' in course_name
        elif 'جيولوج' in specialization:
            return course_subject in ['geology', 'chemistry'] or 'جيولوج' in course_name
        elif 'رياضيات' in specialization:
            return course_subject in ['math', 'computer_science'] or 'رياض' in course_name
        elif 'فيزياء' in specialization:
            return course_subject in ['physics', 'math'] or 'فيزياء' in course_name
        
        return False

    def _calculate_course_relevance_score(self, course, specialization):
        """حساب نقاط صلة المقرر بالتخصص"""
        score = 0
        course_subject = course['subject_type']
        
        # النقاط الأساسية حسب نوع المادة
        if 'حيوان' in specialization and course_subject == 'biology':
            score += 10
        elif 'كيمياء' in specialization and course_subject == 'chemistry':
            score += 10
        elif 'رياضيات' in specialization and course_subject == 'math':
            score += 10
        elif 'فيزياء' in specialization and course_subject == 'physics':
            score += 10
        elif 'جيولوج' in specialization and course_subject == 'geology':
            score += 10
        
        # نقاط إضافية للمقررات الإجبارية
        if course['is_mandatory']:
            score += 5
        
        # نقاط إضافية حسب الترم (المقررات المبكرة أولوية)
        if course['semester'] <= 4:
            score += 3
        elif course['semester'] <= 6:
            score += 2
        else:
            score += 1
            
        return score

    def _get_specialization_courses(self, student, specialization, semester, max_credits):
        """الحصول على مقررات تخصص معين محسنة"""
        # الحصول على المقررات المرتبطة بالتخصص
        relevant_courses = self._get_specialization_related_courses(student, specialization)
        
        # تصفية المقررات حسب الترم
        semester_courses = [
            course for course in relevant_courses 
            if course['semester'] == semester
        ]
        
        # إذا لم توجد مقررات للترم المحدد، اختيار من الترمات المتاحة
        if not semester_courses:
            semester_courses = [
                course for course in relevant_courses 
                if course['semester'] >= semester  # الترمات اللاحقة
            ]
        
        # اختيار المقررات بناءً على حد الساعات
        selected_courses = []
        total_credits = 0
        
        # إعطاء أولوية للمقررات الإجبارية ذات الصلة العالية
        mandatory_courses = [c for c in semester_courses if c['is_mandatory']]
        elective_courses = [c for c in semester_courses if not c['is_mandatory']]
        
        # إضافة المقررات الإجبارية أولاً
        for course in mandatory_courses:
            if total_credits + course['credits'] <= max_credits:
                selected_courses.append(course)
                total_credits += course['credits']
                
        # إضافة المقررات الاختيارية حسب الأهمية
        for course in elective_courses:
            if total_credits + course['credits'] <= max_credits and len(selected_courses) < 6:
                selected_courses.append(course)
                total_credits += course['credits']
                
        # إذا لم نصل للحد الأقصى، إضافة مقررات عامة
        if total_credits < max_credits:
            general_courses = self._get_general_backup_courses(student, semester, max_credits - total_credits)
            for course in general_courses:
                if course['course_id'] not in [c['course_id'] for c in selected_courses]:
                    if total_credits + course['credits'] <= max_credits and len(selected_courses) < 6:
                        selected_courses.append(course)
                        total_credits += course['credits']
                
        return selected_courses

    def _get_general_backup_courses(self, student, semester, remaining_credits):
        """الحصول على مقررات عامة احتياطية مع البيانات الكاملة - محسن"""
        available_courses = self._get_available_courses_for_division(student.DivisionId)
        completed_courses = self._get_completed_course_ids(student.Id)
        
        # تصفية المقررات غير المكتملة
        backup_courses = []
        
        for course_data in available_courses:
            if course_data['course_id'] not in completed_courses and course_data['credits'] <= remaining_credits:
                # الحصول على بيانات المقرر الكاملة من قاعدة البيانات
                course = Courses.query.get(course_data['course_id'])
                if course:
                    backup_courses.append({
                        'course_id': course.Id,
                        'course_name': course.Name,
                        'course_code': course.Code,
                        'credits': course.Credits,
                        'is_mandatory': course_data['is_mandatory'],
                        'semester': course_data['semester']
                    })
        
        # ترتيب حسب الأهمية (إجباري أولاً، ثم حسب الترم)
        backup_courses.sort(key=lambda x: (not x['is_mandatory'], x['semester']))
        
        # إزالة الحقول الإضافية وإرجاع البيانات النظيفة
        clean_courses = []
        for course in backup_courses[:3]:  # أقصى 3 مقررات احتياطية
            clean_courses.append({
                'course_id': course['course_id'],
                'course_name': course['course_name'],
                'course_code': course['course_code'],
                'credits': course['credits']
            })
        
        return clean_courses

    def _get_completed_course_ids(self, student_id):
        """الحصول على قائمة بمعرفات المقررات المكتملة - محسن"""
        student_data = self._get_student_data_bulk(student_id)
        if student_data:
            return self._get_completed_course_ids_fast(student_data['enrollments'])
        return []

    def _calculate_course_ratio(self, courses):
        """حساب نسبة المقررات الإجبارية للاختيارية"""
        mandatory_count = len([c for c in courses if c['is_mandatory']])
        elective_count = len([c for c in courses if not c['is_mandatory']])
        
        return {
            'mandatory': mandatory_count,
            'elective': elective_count,
            'ratio': f"{mandatory_count}:{elective_count}" if elective_count > 0 else f"{mandatory_count}:0"
        }

    def _error_response(self, message):
        """إنشاء استجابة خطأ موحدة"""
        return {
            'message': message,
            'status': 'error'
        }

    def get_division_recommendations(self, student_id):
        """الحصول على توصيات التخصص للطالب"""
        from models import Students
        
        try:
            student = Students.query.get(student_id)
            if not student:
                return self._error_response('الطالب غير موجود')
            
            # تحديد المرحلة الحالية للطالب
            current_stage = self._determine_student_stage(student)
            
            # الحصول على التوصيات المناسبة حسب المرحلة
            recommendations = self._get_stage_appropriate_recommendations(student, current_stage)
            
            return {
                'message': 'تم الحصول على توصيات التخصص بنجاح',
                'status': 'success',
                    'student_info': self._get_basic_student_info(student),
                    'current_stage': current_stage,
                    'recommendations': recommendations
            }
            
        except Exception as e:
            return self._error_response(f'خطأ في الحصول على التوصيات: {str(e)}')

    def _determine_student_stage(self, student):
        """تحديد المرحلة الحالية للطالب بناءً على الفصل الدراسي والشعبة"""
        current_division = student.division.Name
        semester = student.Semester
        
        # العام الأول - جميع المسارات
        if semester <= 2:
            if current_division == 'مجموعة العلوم الطبيعية':
                return 'العام الأول - مسار العلوم الطبيعية'
            elif current_division == 'مجموعة العلوم البيولوجية والكيميائية':
                return 'العام الأول - مسار العلوم البيولوجية'
            elif current_division == 'مجموعة العلوم الجيولوجية والكيميائية':
                return 'العام الأول - مسار العلوم الجيولوجية'
        
        # العام الثاني
        elif semester <= 4:
            if current_division == 'مجموعة العلوم الطبيعية':
                return 'العام الثاني - يحتاج اختيار تشعيب متوسط'
            elif current_division in ['الرياضيات والفيزياء', 'الكيمياء والفيزياء']:
                return f'العام الثاني - التشعيب المتوسط: {current_division}'
            elif current_division == 'مجموعة العلوم البيولوجية والكيميائية':
                return 'العام الثاني - مسار العلوم البيولوجية'
            elif current_division == 'مجموعة العلوم الجيولوجية والكيميائية':
                return 'العام الثاني - مسار العلوم الجيولوجية'
        
        # العام الثالث والرابع
        else:
            if current_division in ['الرياضيات والفيزياء', 'الكيمياء والفيزياء']:
                return f'العام الثالث/الرابع - يحتاج اختيار تخصص نهائي من {current_division}'
            elif current_division == 'مجموعة العلوم البيولوجية والكيميائية':
                return 'العام الثالث/الرابع - يحتاج اختيار تخصص نهائي من البيولوجية'
            elif current_division == 'مجموعة العلوم الجيولوجية والكيميائية':
                return 'العام الثالث/الرابع - يحتاج اختيار تخصص نهائي من الجيولوجية'
            else:
                # طالب في تخصص نهائي بالفعل
                return f'التخصص النهائي: {current_division}'
        
        return 'مرحلة غير محددة'

    def _get_stage_appropriate_recommendations(self, student, current_stage):
        """الحصول على التوصيات المناسبة حسب مرحلة الطالب مع تحليل الأداء"""
        current_division = student.division.Name
        
        # العام الأول - لا يحتاج توصيات تخصص
        if 'العام الأول' in current_stage:
            return {
                'note': 'الطالب في العام الأول، سيتم اختيار التخصص في السنوات اللاحقة',
                'next_step': self._get_next_step_recommendation(current_division)
            }
        
        # العام الثاني - اختيار التشعيب المتوسط لمسار العلوم الطبيعية
        elif 'يحتاج اختيار تشعيب متوسط' in current_stage:
            return self._recommend_intermediate_specialization(student)
        
        # العام الثالث/الرابع - اختيار التخصص النهائي
        elif 'يحتاج اختيار تخصص نهائي' in current_stage:
            performance = self._analyze_student_performance(student)
            
            # تحديد التخصصات المتاحة حسب المسار
            available_specializations = []
            if 'البيولوجية' in current_stage:
                available_specializations = [
                    'علم الحيوان',
                    'النبات والكيمياء', 
                    'علم الحيوان والكيمياء',
                    'الكيمياء والكيمياء الحيوية'
                ]
            elif 'الجيولوجية' in current_stage:
                available_specializations = ['الجيولوجيا والكيمياء']
            
            if not available_specializations:
                return {
                    'note': 'لا توجد تخصصات متاحة',
                    'error': 'خطأ في تحديد التخصصات المتاحة'
                }
            
            return self._recommend_final_specialization(
                student, current_division, available_specializations, performance
            )
        
        # طالب في تشعيب متوسط - هنا المشكلة اللي كنت بتتكلمي عليها
        elif 'التشعيب المتوسط' in current_stage:
            # تحليل أداء الطالب في التشعيب المتوسط
            performance = self._analyze_student_performance(student)
            available_specializations = self._get_valid_final_specializations(current_division)
            
            if not available_specializations:
                return {
                    'note': f'لا توجد تخصصات متاحة للتشعيب: {current_division}',
                    'error': 'خطأ في النظام'
                }
            
            # حساب التوصية الذكية بناءً على الأداء
            specialization_recommendation = self._recommend_specialization(
                student, available_specializations, performance
            )
            
            return {
                'current_status': f'الطالب في التشعيب المتوسط: {current_division}',
                'smart_recommendation': {
                    'recommended_specialization': specialization_recommendation['recommended_specialization']['specialization'],
                    'confidence_level': specialization_recommendation['recommended_specialization']['recommendation_level'],
                    'reasoning': self._format_reasoning_with_calculation(
                        specialization_recommendation['recommended_specialization']['reasoning'],
                        performance
                    ),
                    'suitability_score': specialization_recommendation['recommended_specialization']['suitability_score']
                },
                'alternative_options': [
                    {
                        'specialization': rec['specialization'],
                        'suitability_score': rec['suitability_score'],
                        'recommendation_level': rec['recommendation_level'],
                        'brief_reasoning': self._format_reasoning_with_calculation(rec['reasoning'][:2], performance)
                    }
                    for rec in specialization_recommendation['all_recommendations'][1:]  # باقي الخيارات
                ],
                'next_step': 'يُنصح بالتقديم للتخصص الموصى به في العام الثالث',
                'note': f'التوصية مبنية على تحليل أدائك الأكاديمي (المعدل التراكمي: {performance["overall_gpa"]})'
            }
        
        # طالب في تخصص نهائي
        elif 'التخصص النهائي' in current_stage:
            return {
                'current_status': f'الطالب في التخصص النهائي: {current_division}',
                'note': 'التخصص مكتمل - التركيز على الأداء الأكاديمي والتحضير للتخرج'
            }
        
        return {'note': 'لا توجد توصيات متاحة حالياً'}

    def _format_reasoning_with_calculation(self, reasons, performance):
        """تنسيق الأسباب بشكل مبسط وواضح"""
        formatted_reasons = []
        
        for reason in reasons:
            # تبسيط النصوص بدون تكرار أو تفاصيل زائدة
            if 'رياضيات' in reason and 'متوسط' in reason:
                math_avg = performance['math_performance_avg']
                formatted_reason = f"أداء جيد في الرياضيات: {math_avg}"
            elif 'فيزياء' in reason and 'متوسط' in reason:
                physics_avg = performance['physics_performance_avg']
                formatted_reason = f"أداء مناسب في الفيزياء: {physics_avg}"
            elif 'كيمياء' in reason and 'متوسط' in reason:
                chemistry_avg = performance['chemistry_performance_avg']
                formatted_reason = f"أداء في الكيمياء: {chemistry_avg}"
            elif 'معدل تراكمي' in reason:
                formatted_reason = f"المعدل التراكمي العام: {performance['overall_gpa']}"
            else:
                # الاحتفاظ بالأسباب الأخرى بشكل مبسط
                formatted_reason = reason.replace('/4.0', '').replace('محسوب من', '').replace('مقررات', '').replace('مقرر', '')
                # تنظيف النص من الأقواس والتفاصيل الزائدة
                formatted_reason = formatted_reason.split('(')[0].strip()
                
            formatted_reasons.append(formatted_reason)
        
        # إزالة التكرارات
        unique_reasons = []
        for reason in formatted_reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)
            
        return unique_reasons

    def _get_next_step_recommendation(self, current_division):
        """تحديد الخطوة التالية للطالب"""
        if current_division == 'مجموعة العلوم الطبيعية':
            return 'في العام الثاني يجب اختيار تشعيب متوسط: الرياضيات والفيزياء أو الكيمياء والفيزياء'
        elif current_division == 'مجموعة العلوم البيولوجية والكيميائية':
            return 'في العام الثالث يجب اختيار تخصص نهائي من التخصصات البيولوجية'
        elif current_division == 'مجموعة العلوم الجيولوجية والكيميائية':
            return 'في العام الثالث يجب اختيار تخصص: الجيولوجيا والكيمياء'
        return 'غير محدد'

    def _get_final_year_advice(self, student, performance):
        """نصائح أكاديمية للطلاب في السنة النهائية"""
        advice = []
        current_gpa = performance['overall_gpa']
        current_semester = student.Semester
        
        # نصائح حسب المعدل
        if current_gpa >= 3.5:
            advice.append('أداء ممتاز! استمر على نفس المستوى')
            advice.append('فكر في التقديم لبرامج الدراسات العليا')
        elif current_gpa >= 3.0:
            advice.append('أداء جيد جداً، حاول الحفاظ على المعدل أو تحسينه')
            advice.append('يمكنك التقديم لبرامج الدراسات العليا')
        elif current_gpa >= 2.5:
            advice.append('أداء جيد، ركز على المواد الأساسية في تخصصك')
            advice.append('حاول تحسين المعدل في الترمات المتبقية')
        elif current_gpa >= 2.0:
            advice.append('تحتاج لبذل جهد إضافي لتحسين المعدل')
            advice.append('ركز على اجتياز جميع المواد بدرجات مقبولة')
        else:
            advice.append('وضع أكاديمي حرج - تحتاج مساعدة فورية')
            advice.append('تواصل مع المرشد الأكاديمي لوضع خطة علاجية')
        
        # نصائح حسب الترم
        if current_semester >= 7:
            advice.append('قارب على التخرج - تأكد من استكمال جميع متطلبات التخصص')
            advice.append('ابدأ التحضير لمشروع التخرج إن وجد')
        
        # نصائح حسب أقوى وأضعف المواد
        strongest = self._get_strongest_subject(performance)
        weakest = self._get_weakest_subject(performance)
        
        if strongest['subject'] != 'غير محدد':
            advice.append(f'نقطة قوتك في {strongest["subject"]} - استغلها في مشاريعك')
        
        if weakest['subject'] != 'غير محدد' and weakest['average'] < 2.5:
            advice.append(f'تحتاج تحسين في {weakest["subject"]} - اطلب مساعدة إضافية')
            
        return advice

    def get_course_schedule(self, student_id, semester_count=None):
        """الحصول على الخطة الدراسية الذكية حسب مرحلة الطالب"""
        try:
            from models import Students
            
            # الحصول على بيانات الطالب
            student = Students.query.get(student_id)
            if not student:
                return self._error_response('الطالب غير موجود')
            
            # تحديد المرحلة والتخصص الحالي
            current_stage = self._determine_student_stage(student)
            current_semester = student.Semester
            current_gpa = self._calculate_student_gpa(student)
            max_credits = self._get_max_credits(current_gpa)
            
            student_info = {
                'id': student.Id,
                'name': student.Name,
                'current_semester': current_semester,
                'division': student.division.Name if student.division else 'غير محدد',
                'credits_completed': student.CreditsCompleted,
                'gpa': current_gpa,
                'max_credits_per_semester': max_credits
            }
            
            # إنشاء الخطة حسب المرحلة
            if 'العام الأول' in current_stage or 'مجموعة العلوم الطبيعية' in current_stage:
                # طالب في المرحلة العامة
                return self._create_general_student_plan(student, student_info, current_stage)
                
            elif 'آخر ترم قبل التخصص' in current_stage or current_semester == 2:
                # طالب علوم طبيعية في الترم الثاني - يحتاج خطط متعددة
                return self._create_pre_specialization_plans(student, student_info)
                
            elif 'التشعيب المتوسط' in current_stage or current_semester == 4:
                # طالب في الترم الرابع - يحتاج خطط متعددة للتخصصات النهائية
                return self._create_intermediate_stage_plans(student, student_info, current_stage)
                
            elif 'التخصص النهائي' in current_stage or current_semester >= 5:
                # طالب في التخصص النهائي - خطة واحدة لباقي الترمات
                return self._create_final_stage_plan(student, student_info, current_stage)
                
            else:
                return self._error_response('لا يمكن تحديد المرحلة الدراسية للطالب')
                
        except Exception as e:
            return self._error_response(f'خطأ في إنشاء الخطة الدراسية: {str(e)}')

    def _create_general_student_plan(self, student, student_info, current_stage):
        """إنشاء خطة دراسية للطلاب في المرحلة العامة"""
        current_semester = student.Semester
        max_credits = student_info['max_credits_per_semester']
        
        # تحديد عدد الترمات المتبقية في المرحلة العامة
        if 'مجموعة العلوم الطبيعية' in current_stage:
            remaining_semesters = 2 - current_semester  # ترمين في العلوم الطبيعية
        else:
            remaining_semesters = 4 - current_semester  # أربع ترمات في البيولوجية/الجيولوجية
        
        if remaining_semesters <= 0:
            return self._error_response('الطالب انتهى من المرحلة العامة')
        
        semester_plans = {}
        
        for i in range(remaining_semesters):
            semester_number = current_semester + i + 1
            semester_key = f'semester_{semester_number}'
            
            # الحصول على المقررات للترم
            courses = self._get_general_courses_for_semester(student, semester_number, max_credits)
            
            semester_plans[semester_key] = {
                'semester_number': semester_number,
                'semester_name': f'الترم {semester_number}',
                'stage': 'المرحلة العامة',
                'courses': courses,
                'total_credits': sum(course.get('credits', 0) for course in courses),
                'note': 'مقررات عامة - لا يوجد تخصص بعد'
            }
            
            return {
            'student_info': student_info,
            'plan_type': 'المرحلة العامة',
            'current_stage': current_stage,
            'remaining_semesters': remaining_semesters,
            'semester_plans': semester_plans,
            'note': 'خطة دراسية للمرحلة العامة - سيتم اختيار التخصص لاحقاً'
        }

    def _create_pre_specialization_plans(self, student, student_info):
        """إنشاء خطط متعددة للطلاب قبل اختيار التخصص المتوسط"""
        # الحصول على التوصيات من division-recommendations
        recommendations = self.get_division_recommendations(student.Id)
        
        if 'error' in recommendations:
            return self._error_response('خطأ في الحصول على التوصيات')
        
        recommended_path = None
        alternative_path = None
        
        # استخراج المسار الموصى به والمسار البديل
        if 'smart_recommendation' in recommendations.get('data', {}):
            recommended_spec = recommendations['data']['smart_recommendation']['recommended_specialization']
            recommended_path = recommended_spec
            
            # الحصول على المسار البديل
            alternatives = recommendations['data'].get('alternative_options', [])
            if alternatives:
                alternative_path = alternatives[0]['specialization']
        
        # إنشاء خطط متعددة
        plans = {}
        
        if recommended_path:
            plans['recommended_plan'] = self._create_specialization_path_plan(
                student, student_info, recommended_path, 'المسار الموصى به'
            )
        
        if alternative_path:
            plans['alternative_plan'] = self._create_specialization_path_plan(
                student, student_info, alternative_path, 'المسار البديل'
            )
        
        return {
            'student_info': student_info,
            'plan_type': 'خطط متعددة قبل التخصص المتوسط',
            'current_stage': 'آخر ترم قبل التخصص المتوسط',
            'available_plans': plans,
            'recommendation': f'يُنصح بالمسار: {recommended_path}' if recommended_path else 'لا توجد توصية محددة',
            'note': 'اختر المسار المناسب لك بناءً على أدائك وتوصيات النظام'
        }

    def _create_intermediate_stage_plans(self, student, student_info, current_stage):
        """إنشاء خطط متعددة للطلاب في التشعيب المتوسط"""
        current_division = student.division.Name if student.division else 'غير محدد'
        
        # الحصول على التخصصات النهائية المتاحة
        available_specializations = self._get_valid_final_specializations(current_division)
        
        if not available_specializations:
            return self._error_response(f'لا توجد تخصصات نهائية متاحة للتشعيب: {current_division}')
        
        # الحصول على التوصيات
        recommendations = self.get_division_recommendations(student.Id)
        recommended_spec = None
        
        if 'smart_recommendation' in recommendations.get('data', {}):
            recommended_spec = recommendations['data']['smart_recommendation']['recommended_specialization']
        
        # إنشاء خطط لكل التخصصات المتاحة
        plans = {}
        
        for specialization in available_specializations:
            plan_type = 'المسار الموصى به' if specialization == recommended_spec else 'مسار بديل'
            plans[f'plan_{specialization.lower().replace(" ", "_")}'] = self._create_final_specialization_path_plan(
                student, student_info, specialization, plan_type
            )
            
        return {
            'student_info': student_info,
            'plan_type': 'خطط متعددة للتخصصات النهائية',
            'current_stage': current_stage,
            'available_plans': plans,
            'recommendation': f'يُنصح بالتخصص: {recommended_spec}' if recommended_spec else 'لا توجد توصية محددة',
            'note': 'اختر التخصص النهائي المناسب لك بناءً على أدائك وأهدافك المهنية'
        }

    def _create_final_stage_plan(self, student, student_info, current_stage):
        """إنشاء خطة دراسية للطلاب في التخصص النهائي"""
        current_semester = student.Semester
        current_specialization = student.division.Name if student.division else 'غير محدد'
        max_credits = student_info['max_credits_per_semester']
        
        # حساب الترمات المتبقية للتخرج
        total_semesters = 8
        remaining_semesters = total_semesters - current_semester
        
        semester_plans = {}
        
        # إنشاء خطط للترمات المتبقية
        for i in range(remaining_semesters):
            semester_number = current_semester + i + 1
            semester_key = f'semester_{semester_number}'
            
            # الحصول على مقررات التخصص للترم
            courses = self._get_specialization_courses_for_semester(
                student, current_specialization, semester_number, max_credits
            )
            
            semester_plans[semester_key] = {
                'semester_number': semester_number,
                'semester_name': f'الترم {semester_number}',
                'stage': f'التخصص النهائي: {current_specialization}',
                'courses': courses,
                'total_credits': sum(course.get('credits', 0) for course in courses),
                'note': f'مقررات تخصص {current_specialization}'
            }
        
        # إضافة ملاحظة خاصة للترم الأخير
        if remaining_semesters > 0:
            last_semester_key = f'semester_{current_semester + remaining_semesters}'
            if last_semester_key in semester_plans:
                semester_plans[last_semester_key]['note'] += ' - ترم التخرج'
                semester_plans[last_semester_key]['graduation_note'] = 'تأكد من استكمال جميع متطلبات التخرج'
        
        return {
            'student_info': student_info,
            'plan_type': f'خطة التخصص النهائي: {current_specialization}',
            'current_stage': current_stage,
            'remaining_semesters': remaining_semesters,
            'semester_plans': semester_plans,
            'graduation_info': {
                'expected_graduation_semester': current_semester + remaining_semesters,
                'total_semesters_to_complete': remaining_semesters,
                'note': 'تأكد من اجتياز جميع المقررات المطلوبة للتخرج'
            }
        }

    def _create_specialization_path_plan(self, student, student_info, specialization, plan_type):
        """إنشاء خطة دراسية لمسار تخصص معين"""
        current_semester = student.Semester
        max_credits = student_info['max_credits_per_semester']
        
        # إنشاء خطة للترمات القادمة في هذا المسار
        semester_plans = {}
        
        # بدء من الترم التالي
        for i in range(6):  # 6 ترمات متبقية من الترم 3 إلى 8
            semester_number = current_semester + i + 1
            if semester_number > 8:
                break
                
            semester_key = f'semester_{semester_number}'
            
            if semester_number <= 4:
                # ترمات التشعيب المتوسط
                courses = self._get_intermediate_specialization_courses(
                    student, specialization, semester_number, max_credits
                )
                stage_name = f'التشعيب المتوسط: {specialization}'
            else:
                # ترمات التخصص النهائي
                final_specs = self._get_valid_final_specializations(specialization)
                if final_specs:
                    recommended_final = final_specs[0]  # أول تخصص متاح
                    courses = self._get_specialization_courses_for_semester(
                        student, recommended_final, semester_number, max_credits
                    )
                    stage_name = f'التخصص النهائي: {recommended_final}'
                else:
                    courses = []
                    stage_name = 'غير محدد'
            
            semester_plans[semester_key] = {
                'semester_number': semester_number,
                'semester_name': f'الترم {semester_number}',
                'stage': stage_name,
                'courses': courses,
                'total_credits': sum(course.get('credits', 0) for course in courses),
                'note': f'مقررات {plan_type}'
            }
        
        return {
            'specialization': specialization,
            'plan_type': plan_type,
            'semester_plans': semester_plans,
            'total_semesters': len(semester_plans)
        }

    def _create_final_specialization_path_plan(self, student, student_info, specialization, plan_type):
        """إنشاء خطة دراسية للتخصص النهائي"""
        current_semester = student.Semester
        max_credits = student_info['max_credits_per_semester']
        
        # الحصول على جميع المقررات المتاحة مرة واحدة
        student_data = self._get_student_data_bulk(student.Id)
        completed_course_ids = self._get_completed_course_ids_fast(student_data['enrollments'])
        available_courses = self._get_all_division_data_bulk(student.DivisionId)
        
        # تصفية المقررات حسب التخصص
        specialization_courses = self._filter_specialization_courses_fast(available_courses, specialization)
        if not specialization_courses:
            specialization_courses = available_courses
        
        # تتبع المقررات المقترحة لتجنب التكرار
        suggested_course_ids = set()
        semester_plans = {}
        
        # بدء من الترم التالي (5 إلى 8)
        for i in range(4):  # 4 ترمات للتخصص النهائي
            semester_number = current_semester + i + 1
            if semester_number > 8:
                break
                
            semester_key = f'semester_{semester_number}'
            
            courses = self._get_specialization_courses_for_specific_semester(
                specialization_courses, completed_course_ids, suggested_course_ids, 
                semester_number, max_credits, specialization
            )
            
            # إضافة المقررات المقترحة إلى مجموعة التتبع
            for course in courses:
                if course.get('course_id'):
                    suggested_course_ids.add(course['course_id'])
            
            semester_plans[semester_key] = {
                'semester_number': semester_number,
                'semester_name': f'الترم {semester_number}',
                'stage': f'التخصص النهائي: {specialization}',
                'courses': courses,
                'total_credits': sum(course.get('credits', 0) for course in courses),
                'note': f'مقررات التخصص النهائي - {plan_type}'
            }
        
        return {
            'specialization': specialization,
            'plan_type': plan_type,
            'semester_plans': semester_plans,
            'total_semesters': len(semester_plans)
        }

    def _get_specialization_courses_for_specific_semester(self, available_courses, completed_course_ids, 
                                                         suggested_course_ids, semester_number, max_credits, specialization):
        """الحصول على مقررات مخصصة لترم معين مع تجنب التكرار"""
        try:
            # تقسيم المقررات حسب الأولوية والترم
            high_priority_courses = []
            medium_priority_courses = []
            low_priority_courses = []
            
            for course_data in available_courses:
                course_id = course_data.get('course_id')
                
                # تخطي المقررات المكتملة أو المقترحة مسبقاً
                if (course_id in completed_course_ids or 
                    course_id in suggested_course_ids):
                    continue
                
                course_semester = course_data.get('semester', 1)
                is_mandatory = course_data.get('is_mandatory', False)
                
                # تصنيف المقررات حسب الأولوية والترم
                if is_mandatory and course_semester <= semester_number:
                    high_priority_courses.append(course_data)
                elif (course_semester == semester_number or 
                      course_semester == semester_number - 1):
                    medium_priority_courses.append(course_data)
                elif self._is_course_relevant_to_specialization_fast(course_data, specialization):
                    medium_priority_courses.append(course_data)
                else:
                    low_priority_courses.append(course_data)
            
            # ترتيب كل مجموعة حسب معايير مختلفة
            high_priority_courses.sort(key=lambda x: (x.get('semester', 99), -x.get('credits', 0)))
            medium_priority_courses.sort(key=lambda x: (
                not self._is_course_relevant_to_specialization_fast(x, specialization),
                x.get('semester', 99), 
                -x.get('credits', 0)
            ))
            low_priority_courses.sort(key=lambda x: (x.get('semester', 99), -x.get('credits', 0)))
            
            # بناء قائمة المقررات النهائية
            selected_courses = []
            current_credits = 0
            
            # أولاً: المقررات عالية الأولوية
            for course_data in high_priority_courses:
                if current_credits >= max_credits:
                    break
                course = self._format_course_data(course_data)
                if current_credits + course['credits'] <= max_credits:
                    selected_courses.append(course)
                    current_credits += course['credits']
            
            # ثانياً: المقررات متوسطة الأولوية
            for course_data in medium_priority_courses:
                if current_credits >= max_credits:
                    break
                course = self._format_course_data(course_data)
                if current_credits + course['credits'] <= max_credits:
                    selected_courses.append(course)
                    current_credits += course['credits']
            
            # ثالثاً: المقررات منخفضة الأولوية إذا لم نصل للحد الأقصى
            for course_data in low_priority_courses:
                if current_credits >= max_credits or len(selected_courses) >= 7:
                    break
                course = self._format_course_data(course_data)
                if current_credits + course['credits'] <= max_credits:
                    selected_courses.append(course)
                    current_credits += course['credits']
            
            # ضمان الحد الأدنى من المقررات
            if len(selected_courses) == 0:
                # كملجأ أخير، خذ أي مقررات متاحة
                fallback_courses = [c for c in available_courses 
                                  if (c.get('course_id') not in completed_course_ids and 
                                      c.get('course_id') not in suggested_course_ids)][:4]
                
                for course_data in fallback_courses:
                    selected_courses.append(self._format_course_data(course_data))
            
            return selected_courses[:7]  # حد أقصى 7 مقررات
            
        except Exception as e:
            return [{'error': f'خطأ في جلب المقررات للترم {semester_number}: {str(e)}'}]

    def _format_course_data(self, course_data):
        """تنسيق بيانات المقرر بصيغة موحدة"""
        return {
            'course_id': course_data.get('course_id'),
            'course_name': course_data.get('name', 'مقرر غير محدد'),
            'course_code': course_data.get('code', 'غير محدد'),
            'credits': course_data.get('credits', 3),
            'department': course_data.get('department_name', 'غير محدد'),
            'is_mandatory': course_data.get('is_mandatory', False)
        }

    def _get_specialization_courses_for_semester(self, student, specialization, semester, max_credits):
        """الحصول على مقررات التخصص لترم معين مع البيانات الكاملة - محسن"""
        try:
            # استخدام البيانات المحملة مسبقاً
            student_data = self._get_student_data_bulk(student.Id)
            completed_course_ids = self._get_completed_course_ids_fast(student_data['enrollments'])
            
            # الحصول على مقررات الشعبة من الكاش
            available_courses = self._get_all_division_data_bulk(student.DivisionId)
            
            # تصفية المقررات حسب التخصص أولاً
            specialization_courses = self._filter_specialization_courses_fast(available_courses, specialization)
            
            # إذا لم نجد مقررات متخصصة، استخدم المقررات العامة للشعبة
            if not specialization_courses:
                specialization_courses = available_courses
            
            # استخدام دالة التحديد المحسنة للمقررات
            empty_suggested = set()  # لا توجد مقررات مقترحة مسبقاً في هذا السياق
            
            filtered_courses = self._get_specialization_courses_for_specific_semester(
                specialization_courses, completed_course_ids, empty_suggested, 
                semester, max_credits, specialization
            )
            
            return filtered_courses
            
        except Exception as e:
            # في حالة الخطأ، أرجع قائمة فارغة مع رسالة
            return [{'error': f'خطأ في جلب المقررات: {str(e)}'}]

    def _filter_specialization_courses_fast(self, available_courses, specialization):
        """تصفية مقررات التخصص بسرعة من البيانات المحملة"""
        relevant_courses = []
        
        # تعريف كلمات مفتاحية أكثر تفصيلاً لكل تخصص
        specialization_detailed_keywords = {
            'الرياضيات الخاصة': {
                'primary': ['رياضيات', 'حساب', 'جبر', 'هندسة', 'إحصاء', 'تفاضل', 'تكامل'],
                'secondary': ['منطق', 'نظرية', 'خطي'],
                'departments': ['قسم الرياضيات']
            },
            'الفيزياء الخاصة': {
                'primary': ['فيزياء', 'ميكانيكا', 'كهرباء', 'مغناطيس', 'بصريات', 'ضوء'],
                'secondary': ['طاقة', 'حركة', 'موجات', 'ذرية'],
                'departments': ['قسم الفيزياء']
            },
            'الرياضيات وعلوم الحاسب': {
                'primary': ['رياضيات', 'حاسب', 'برمجة', 'خوارزميات', 'بيانات'],
                'secondary': ['منطق', 'نظم', 'تحليل', 'تصميم'],
                'departments': ['قسم الرياضيات', 'قسم علوم الحاسب']
            },
            'الأحياء': {
                'primary': ['أحياء', 'حيوان', 'نبات', 'خلية', 'جزيئي'],
                'secondary': ['وراثة', 'تطور', 'بيئة', 'تشريح'],
                'departments': ['قسم علم الحيوان', 'قسم النبات']
            },
            'الكيمياء': {
                'primary': ['كيمياء', 'تحليلي', 'عضوي', 'فيزيائي'],
                'secondary': ['معادن', 'تفاعل', 'محلول', 'تركيب'],
                'departments': ['قسم الكيمياء']
            },
            'الجيولوجيا': {
                'primary': ['جيولوجيا', 'معادن', 'صخور', 'أرض'],
                'secondary': ['طبقات', 'حفريات', 'بترول', 'مياه'],
                'departments': ['قسم الجيولوجيا']
            }
        }
        
        # الحصول على كلمات التخصص
        spec_keywords = specialization_detailed_keywords.get(specialization, {
            'primary': [specialization.lower()],
            'secondary': [],
            'departments': []
        })
        
        for course in available_courses:
            relevance_score = 0
            course_name = course.get('name', '').lower()
            department_name = course.get('department_name', '').lower()
            
            # فحص الكلمات الأساسية
            for keyword in spec_keywords['primary']:
                if keyword in course_name:
                    relevance_score += 10
                if keyword in department_name:
                    relevance_score += 5
            
            # فحص الكلمات الثانوية
            for keyword in spec_keywords['secondary']:
                if keyword in course_name:
                    relevance_score += 3
                if keyword in department_name:
                    relevance_score += 2
            
            # فحص القسم
            for dept in spec_keywords['departments']:
                if dept.lower() in department_name:
                    relevance_score += 8
            
            # إضافة درجة للمقررات الإجبارية
            if course.get('is_mandatory', False):
                relevance_score += 15
            
            # إضافة المقرر إذا كان ذا صلة
            if relevance_score > 0:
                course['relevance_score'] = relevance_score
                relevant_courses.append(course)
        
        # إذا لم نجد مقررات مرتبطة، أرجع جميع المقررات مع درجات منخفضة
        if not relevant_courses:
            for course in available_courses:
                course['relevance_score'] = 1 if course.get('is_mandatory', False) else 0.5
                relevant_courses.append(course)
        
        # ترتيب حسب الأهمية والصلة
        relevant_courses.sort(key=lambda x: (
            -x.get('relevance_score', 0),  # الأكثر صلة أولاً
            -int(x.get('is_mandatory', False)),  # الإجباري أولاً
            x.get('semester', 99)  # الترم الأقل أولاً
        ))
        
        return relevant_courses

    def _is_course_relevant_to_specialization_fast(self, course, specialization):
        """تحديد صلة المقرر بالتخصص - سريع"""
        course_name = course.get('name', '').lower()
        department_name = course.get('department_name', '').lower()
        
        # قواعد تحديد الصلة - محسنة
        specialization_keywords = {
            'الأحياء': ['أحياء', 'حيوان', 'نبات', 'جزيئي', 'خلوي'],
            'الكيمياء': ['كيمياء', 'تحليلي', 'عضوي', 'فيزيائي'],
            'الفيزياء': ['فيزياء', 'ميكانيكا', 'كهرباء', 'مغناطيس'],
            'الرياضيات': ['رياضيات', 'حساب', 'جبر', 'هندسة'],
            'الجيولوجيا': ['جيولوجيا', 'معادن', 'صخور', 'أرض']
        }
        
        keywords = specialization_keywords.get(specialization, [])
        return any(keyword in course_name or keyword in department_name for keyword in keywords)

    def _calculate_course_relevance_score_fast(self, course, specialization):
        """حساب درجة صلة المقرر بالتخصص - سريع"""
        score = 0
        
        # الدرجات الأساسية
        if course.get('is_mandatory', False):
            score += 10
        
        # درجة التطابق مع التخصص
        if self._is_course_relevant_to_specialization_fast(course, specialization):
            score += 5
        
        # عوامل إضافية
        if course.get('semester', 0) <= 6:  # مقررات الترمات المبكرة لها أولوية
            score += 2
        
        return score

    def _get_fast_backup_courses(self, available_courses, completed_course_ids, remaining_credits):
        """الحصول على مقررات احتياطية بسرعة - محسن"""
        backup_courses = []
        
        # ترتيب المقررات المتاحة حسب الأولوية
        sorted_courses = sorted(
            available_courses,
            key=lambda x: (
                not x.get('is_mandatory', False),  # إجباري أولاً
                x.get('semester', 99),  # ثم حسب الترم
                x.get('credits', 0)     # ثم حسب الساعات
            )
        )
        
        current_remaining = remaining_credits
        
        for course_data in sorted_courses:
            if len(backup_courses) >= 5:  # حد أقصى 5 مقررات احتياطية
                break
                
            course_id = course_data.get('course_id')
            course_credits = course_data.get('credits', 3)  # قيمة افتراضية 3 ساعات
            
            if (course_id not in completed_course_ids and 
                course_credits <= current_remaining):
                
                backup_courses.append({
                    'course_id': course_id,
                    'course_name': course_data.get('name', 'مقرر غير محدد'),
                    'course_code': course_data.get('code', 'غير محدد'),
                    'credits': course_credits,
                    'department': course_data.get('department_name', 'غير محدد'),
                    'is_mandatory': course_data.get('is_mandatory', False)
                })
                current_remaining -= course_credits
        
        # إذا لم نجد مقررات كافية، أضف بعض المقررات بدون تحديد الساعات
        if len(backup_courses) < 3:
            for course_data in sorted_courses:
                if len(backup_courses) >= 5:
                    break
                    
                course_id = course_data.get('course_id')
                if course_id not in completed_course_ids:
                    # تحقق من أن المقرر ليس موجود بالفعل
                    existing_ids = [c.get('course_id') for c in backup_courses]
                    if course_id not in existing_ids:
                        backup_courses.append({
                            'course_id': course_id,
                            'course_name': course_data.get('name', 'مقرر غير محدد'),
                            'course_code': course_data.get('code', 'غير محدد'),
                            'credits': min(course_data.get('credits', 3), 4),  # حد أقصى 4 ساعات
                            'department': course_data.get('department_name', 'غير محدد'),
                            'is_mandatory': course_data.get('is_mandatory', False)
                        })
        
        return backup_courses

    def _get_intermediate_specialization_courses(self, student, specialization, semester, max_credits):
        """الحصول على مقررات التشعيب المتوسط مع البيانات الكاملة"""
        from models import Courses
        
        try:
            # الحصول على المقررات المكتملة للطالب
            completed_course_ids = self._get_completed_course_ids(student.Id)
            
            # الحصول على المقررات العامة للترم
            courses = self._get_courses_for_semester(student, semester, max_credits)
            
            filtered_courses = []
            current_credits = 0
            
            for course_data in courses:
                if current_credits >= max_credits:
                    break
                    
                course_id = course_data.get('course_id') if isinstance(course_data, dict) else getattr(course_data, 'CourseID', None)
                
                if course_id and course_id not in completed_course_ids:
                    course = Courses.query.get(course_id)
                    if course:
                        course_credits = course.Credits
                        if current_credits + course_credits <= max_credits:
                            filtered_courses.append({
                                'course_id': course.Id,
                                'course_name': course.Name,
                                'course_code': course.Code,
                                'credits': course_credits
                            })
                            current_credits += course_credits
            
            return filtered_courses
            
        except Exception as e:
            return []

    def analyze_student_performance(self, student_id):
        """تحليل شامل لأداء الطالب الأكاديمي"""
        from models import Students
        
        try:
            student = Students.query.get(student_id)
            if not student:
                return self._error_response('الطالب غير موجود')
                
            performance = self._analyze_student_performance(student)
            current_stage = self._determine_student_stage(student)
            
            return {
                'message': 'تم تحليل أداء الطالب بنجاح',
                'status': 'success',
                'student_info': self._get_basic_student_info(student),
                'performance_analysis': performance,
                'current_stage': current_stage,
                'academic_standing': self._get_academic_standing(performance['overall_gpa']),
                'recommendations': self._get_performance_recommendations(performance)
            }
            
        except Exception as e:
            return self._error_response(f'خطأ في تحليل الأداء: {str(e)}')
