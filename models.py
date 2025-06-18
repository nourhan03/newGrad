from extensions import db

class AcademicWarnings(db.Model):
    __tablename__ = 'AcademicWarnings'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    StudentId = db.Column(db.Integer, db.ForeignKey('Students.Id'), nullable=False)
    WarningType = db.Column(db.String(50), nullable=False)
    WarningLevel = db.Column(db.Integer, nullable=False)
    Description = db.Column(db.String(255), nullable=False)
    Semester = db.Column(db.String, nullable=False)
    IssueDate = db.Column(db.DateTime, nullable=False)
    ResolvedDate = db.Column(db.DateTime, nullable=True)
    Status = db.Column(db.String(20), nullable=False)
    ActionRequired = db.Column(db.String(255), nullable=False)
    Notes = db.Column(db.String(255), nullable=False)

    student = db.relationship('Students', backref='academic_warnings')

class Attendances(db.Model):
    __tablename__ = 'Attendances'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Date = db.Column(db.DateTime, nullable=False)
    Status = db.Column(db.Boolean, nullable=False)
    ClassesId = db.Column(db.Integer, db.ForeignKey('Classes.Id'), nullable=False)
    StudentId = db.Column(db.Integer, db.ForeignKey('Students.Id'), nullable=False)

    class_session = db.relationship('Classes', backref='attendances')
    student = db.relationship('Students', backref='attendances')

class Classes(db.Model):
    __tablename__ = 'Classes'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    StartTime = db.Column(db.Time, nullable=False)
    EndTime = db.Column(db.Time, nullable=False)
    Day = db.Column(db.String(20), nullable=False)
    Location = db.Column(db.String(100))
    ProfessorId = db.Column(db.Integer, db.ForeignKey('Professors.Id'), nullable=False)
    CourseId = db.Column(db.Integer, db.ForeignKey('Courses.Id'), nullable=False)

    professor = db.relationship('Professors', backref='classes')
    course = db.relationship('Courses', backref='classes')


class CourseDivisions(db.Model):
    __tablename__ = 'CourseDivisions'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    CourseId = db.Column(db.Integer, db.ForeignKey('Courses.Id'), nullable=False)
    DivisionId = db.Column(db.Integer, db.ForeignKey('Divisions.Id'), nullable=False)
    IsMandatory = db.Column(db.Boolean, nullable=False)

  
    course = db.relationship('Courses', backref='course_divisions')
    division = db.relationship('Divisions', backref='course_divisions')


class CoursePrerequisites(db.Model):
    __tablename__ = 'CoursePrerequisites'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    CourseId = db.Column(db.Integer, db.ForeignKey('Courses.Id'), nullable=False)
    PrerequisiteCourseId = db.Column(db.Integer, db.ForeignKey('Courses.Id'), nullable=False)

    
    course = db.relationship('Courses', foreign_keys=[CourseId], backref='prerequisites')
    prerequisite_course = db.relationship('Courses', foreign_keys=[PrerequisiteCourseId])


class Courses(db.Model):
    __tablename__ = 'Courses'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.String(50), nullable=False)
    Code = db.Column(db.String(50), nullable=False)
    Description = db.Column(db.String(250), nullable=False)
    Credits = db.Column(db.Integer, nullable=False)
    Status = db.Column(db.String(50), nullable=False)
    Semester = db.Column(db.Integer, nullable=False)
    MaxSeats = db.Column(db.Integer, nullable=False)
    CurrentEnrolledStudents = db.Column(db.Integer, default=0)
    DepartmentId = db.Column(db.Integer, db.ForeignKey('Departments.Id'), nullable=False)

    department = db.relationship('Departments', backref='courses')


class Departments(db.Model):
    __tablename__ = 'Departments'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.String(50), nullable=False)
   

class Divisions(db.Model):
    __tablename__ = 'Divisions'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.String(50), nullable=False)
    DepartmentId = db.Column(db.Integer, db.ForeignKey('Departments.Id'), nullable=False)

    department = db.relationship('Departments', backref='divisions')


class EnrollmentPeriods(db.Model):
    __tablename__ = 'EnrollmentPeriods'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Semester = db.Column(db.Unicode(50), nullable=False)
    StartDate = db.Column(db.DateTime, nullable=False)
    EndDate = db.Column(db.DateTime, nullable=False)


class Enrollments(db.Model):
    __tablename__ = 'Enrollments'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Semester = db.Column(db.String, nullable=False)
    Exam1Grade = db.Column(db.Numeric(10, 2))
    Exam2Grade = db.Column(db.Numeric(10, 2))
    Grade = db.Column(db.Numeric(10, 2))
    NumberOFSemster = db.Column(db.Integer, nullable=False)
    AddedEnrollmentDate = db.Column(db.Date)
    DeletedEnrollmentDate = db.Column(db.Date)
    StudentId = db.Column(db.Integer, db.ForeignKey('Students.Id'), nullable=False)
    CourseId = db.Column(db.Integer, db.ForeignKey('Courses.Id'), nullable=False)
    IsCompleted = db.Column(db.String(50)) 

    
    student = db.relationship('Students', backref='enrollments')
    course = db.relationship('Courses', backref='enrollments')

class Professors(db.Model):
    __tablename__ = 'Professors'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    FullName = db.Column(db.String(100), nullable=False)
    NationalId = db.Column(db.String(14), unique=True, nullable=False)
    Gender = db.Column(db.String(10), nullable=False)
    DateOfBirth = db.Column(db.Date, nullable=False)
    Address = db.Column(db.String(100))
    Email = db.Column(db.String(100), unique=True, nullable=False)
    Phone = db.Column(db.String(15), unique=True, nullable=False)
    Join_Date = db.Column(db.Date, nullable=False)
    Position = db.Column(db.String(20), nullable=False)
    ImagePath = db.Column(db.String(255), nullable=True)
    DepartmentId = db.Column(db.Integer, db.ForeignKey('Departments.Id'), nullable=False)
    IsHeadOfDepartment = db.Column(db.Boolean, nullable=False)

    department = db.relationship('Departments', backref='professors')

class Students(db.Model):
    __tablename__ = 'Students'
    Id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.String(100), nullable=False)
    NationalId = db.Column(db.String(14), unique=True, nullable=False)
    Gender = db.Column(db.String(10), nullable=False)
    DateOfBirth = db.Column(db.Date, nullable=False)
    Address = db.Column(db.String(100))
    Nationality = db.Column(db.String(50))
    Email = db.Column(db.String(100), unique=True, nullable=False)
    Phone = db.Column(db.String(15), unique=True, nullable=False)
    Semester = db.Column(db.Integer, nullable=False)
    EnrollmentDate = db.Column(db.Date, nullable=False)
    High_School_degree = db.Column(db.Numeric(10, 2), nullable=False)
    High_School_Section = db.Column(db.String(50), nullable=False)
    CreditsCompleted = db.Column(db.Integer, nullable=False)
    ImagePath = db.Column(db.String(255), nullable=True)
    DivisionId = db.Column(db.Integer, db.ForeignKey('Divisions.Id'), nullable=False)
    StudentLevel = db.Column(db.Integer)
    status = db.Column(db.Text, nullable=False)
    GPA1 = db.Column(db.Float)
    GPA2 = db.Column(db.Float)
    GPA3 = db.Column(db.Float)
    GPA4 = db.Column(db.Float)
    GPA5 = db.Column(db.Float)
    GPA6 = db.Column(db.Float)
    GPA7 = db.Column(db.Float)
    GPA8 = db.Column(db.Float)

    division = db.relationship('Divisions', backref='students')
