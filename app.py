from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy import inspect, text, or_
from flask import flash, send_file
import os
import re
import secrets
import string
from werkzeug.utils import secure_filename
from docx import Document

from config import Config
from homework_LLM_grader import PythonCodeGrader
from python_speaking import VoiceAssistant
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///homework.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 文件上传配置
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MATERIAL_FOLDER'] = 'course_materials'  # 课程材料存储目录
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 最大文件大小
app.config['ALLOWED_EXTENSIONS'] = {'txt', 'pdf', 'doc', 'docx'}
app.config['ALLOWED_MATERIAL_EXTENSIONS'] = {'ppt', 'pptx', 'pdf', 'doc', 'docx', 'txt', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'jpg', 'jpeg', 'png', 'gif', 'json', 'xml'}

# 确保上传目录存在
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['MATERIAL_FOLDER']):
    os.makedirs(app.config['MATERIAL_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def allowed_material_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_MATERIAL_EXTENSIONS']

db = SQLAlchemy(app)


def generate_invite_code(length=6):
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def ensure_column_exists(table_name, column_name, ddl_fragment):
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    if column_name not in columns:
        db.session.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {ddl_fragment}'))
        db.session.commit()

# 使用简化的模型定义
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = relationship('User', backref=db.backref('courses', lazy=True))


class CourseEnrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = relationship('Course', backref=db.backref('enrollments', lazy=True, cascade='all, delete-orphan'))
    student = relationship('User', backref=db.backref('course_memberships', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('course_id', 'student_id', name='uq_course_student'),
    )


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    status = db.Column(db.String(20), default='published')
    withdrawn_at = db.Column(db.DateTime, nullable=True)

    teacher = relationship('User', backref=db.backref('assignments', lazy=True))
    course = relationship('Course', backref=db.backref('assignments', lazy=True))


class AssignmentQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    knowledge_point = db.Column(db.String(255), nullable=False)

    assignment = relationship('Assignment', backref=db.backref('questions', lazy=True, cascade='all, delete-orphan'))


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    grade = db.Column(db.String(10), nullable=True)
    ai_score = db.Column(db.Float, nullable=True)
    evaluation_result = db.Column(db.Text, nullable=True)
    teacher_comment = db.Column(db.Text, nullable=True)

    assignment = relationship('Assignment', backref=db.backref('submissions', lazy=True))
    student = relationship('User', backref=db.backref('submissions', lazy=True))


class CourseMaterial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    material_type = db.Column(db.String(50), nullable=False)  # ppt, 教材, 知识点, 知识图谱, 视频
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)  # 文件大小（字节）
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published = db.Column(db.Boolean, default=False)  # 是否已发布

    course = relationship('Course', backref=db.backref('materials', lazy=True, cascade='all, delete-orphan'))
    teacher = relationship('User', backref=db.backref('materials', lazy=True))

# 创建数据库表
with app.app_context():
    # 仅测试用
    #db.drop_all()

    db.create_all()
    ensure_column_exists('assignment', 'course_id', 'course_id INTEGER')
    ensure_column_exists('assignment', 'status', "status TEXT DEFAULT 'published'")
    ensure_column_exists('assignment', 'withdrawn_at', 'withdrawn_at DATETIME')
    ensure_column_exists('submission', 'ai_score', 'ai_score REAL')
    ensure_column_exists('submission', 'evaluation_result', 'evaluation_result TEXT')
    ensure_column_exists('submission', 'teacher_comment', 'teacher_comment TEXT')

    # 创建课程材料表
    db.create_all()

    # 回填缺省值，保证旧数据可用
    db.session.execute(text("UPDATE assignment SET status='published' WHERE status IS NULL"))
    db.session.commit()

    # 添加初始测试用户（在实际使用中应该删除这部分）
    if not User.query.filter_by(username='t1').first():
        teacher = User(username='t1', password='123', role='teacher', name='张老师')
        db.session.add(teacher)

    if not User.query.filter_by(username='s1').first():
        student = User(username='s1', password='123', role='student', name='李同学')
        db.session.add(student)

    if not User.query.filter_by(username='s2').first():
        student2 = User(username='s2', password='123', role='student', name='王同学')
        db.session.add(student2)

    db.session.commit()


@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    # 如果已登录，直接重定向到对应面板
    if 'user_id' in session and session['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    elif 'user_id' in session and session['role'] == 'student':
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username, password=password).first()

        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['name'] = user.name

            if user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            return render_template('login.html', error='用户名或密码错误')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    assignments = Assignment.query.filter_by(teacher_id=session['user_id']).order_by(Assignment.created_at.desc()).all()
    courses = Course.query.filter_by(teacher_id=session['user_id']).order_by(Course.created_at.desc()).all()
    return render_template('teacher_dashboard.html', assignments=assignments, courses=courses)


@app.route('/teacher/profile')
def teacher_profile():
    if 'user_id' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('login'))

    if session.get('role') != 'teacher':
        flash('无权限访问该页面', 'error')
        return redirect(url_for('login'))

    teacher = User.query.get_or_404(session['user_id'])

    # 教师创建的课程
    courses = Course.query.filter_by(teacher_id=teacher.id).order_by(Course.created_at.desc()).all()

    # 每门课程的学生
    course_student_info = []
    for course in courses:
        enrollments = CourseEnrollment.query.filter_by(course_id=course.id).order_by(CourseEnrollment.joined_at.asc()).all()
        students = [enrollment.student for enrollment in enrollments]
        course_student_info.append({
            'course': course,
            'students': students,
            'enrollments': enrollments
        })

    masked_password = '*' * len(teacher.password) if teacher.password else '未设置'

    return render_template(
        'teacher_profile.html',
        teacher=teacher,
        masked_password=masked_password,
        course_student_info=course_student_info
    )


@app.route('/teacher/change_password', methods=['POST'])
def change_teacher_password():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    
    teacher = User.query.get_or_404(session['user_id'])
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not old_password or not new_password or not confirm_password:
        flash('请填写所有字段', 'error')
        return redirect(url_for('teacher_profile'))
    
    if teacher.password != old_password:
        flash('原密码错误', 'error')
        return redirect(url_for('teacher_profile'))
    
    if new_password != confirm_password:
        flash('两次输入的新密码不一致', 'error')
        return redirect(url_for('teacher_profile'))
    
    if len(new_password) < 6:
        flash('新密码长度至少6个字符', 'error')
        return redirect(url_for('teacher_profile'))
    
    try:
        teacher.password = new_password
        db.session.commit()
        flash('密码修改成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'密码修改失败: {str(e)}', 'error')
    
    return redirect(url_for('teacher_profile'))


@app.route('/teacher/delete_account', methods=['POST'])
def delete_teacher_account():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    teacher = User.query.get_or_404(user_id)
    
    try:
        # 获取教师创建的所有课程
        courses = Course.query.filter_by(teacher_id=user_id).all()
        
        # 删除每个课程及其相关内容
        for course in courses:
            # 获取该课程下的所有作业
            assignments = Assignment.query.filter_by(course_id=course.id).all()
            for assignment in assignments:
                # 删除作业的所有提交及其文件
                submissions = Submission.query.filter_by(assignment_id=assignment.id).all()
                for submission in submissions:
                    if submission.file_path and os.path.exists(submission.file_path):
                        try:
                            os.remove(submission.file_path)
                        except Exception as e:
                            print(f"删除文件失败: {e}")
                    db.session.delete(submission)
                # 删除作业的题目
                AssignmentQuestion.query.filter_by(assignment_id=assignment.id).delete(synchronize_session=False)
                # 删除作业
                db.session.delete(assignment)
            
            # 删除选课记录
            CourseEnrollment.query.filter_by(course_id=course.id).delete(synchronize_session=False)
            # 删除课程
            db.session.delete(course)
        
        # 删除教师创建的不属于任何课程的作业
        assignments = Assignment.query.filter_by(teacher_id=user_id).all()
        for assignment in assignments:
            submissions = Submission.query.filter_by(assignment_id=assignment.id).all()
            for submission in submissions:
                if submission.file_path and os.path.exists(submission.file_path):
                    try:
                        os.remove(submission.file_path)
                    except Exception as e:
                        print(f"删除文件失败: {e}")
                db.session.delete(submission)
            AssignmentQuestion.query.filter_by(assignment_id=assignment.id).delete(synchronize_session=False)
            db.session.delete(assignment)
        
        # 删除教师账户
        db.session.delete(teacher)
        db.session.commit()
        
        # 清除session
        session.clear()
        flash('账户已成功注销', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        db.session.rollback()
        flash(f'注销账户时出错: {str(e)}', 'error')
        return redirect(url_for('teacher_profile'))


@app.route('/teacher/create_assignment', methods=['GET', 'POST'])
def create_assignment():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    teacher_courses = Course.query.filter_by(teacher_id=session['user_id']).all()

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        due_date_str = request.form['due_date']
        course_id = request.form.get('course_id')
        publish_action = request.form.get('publish_action', 'publish')

        if not title or not content:
            flash('标题和内容不能为空。', 'error')
            return render_template('create_assignment.html', courses=teacher_courses)

        # 转换日期字符串为日期对象
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
        status = 'draft' if publish_action == 'draft' else 'published'

        new_assignment = Assignment(
            title=title,
            content=content,
            teacher_id=session['user_id'],
            due_date=due_date,
            course_id=int(course_id) if course_id else None,
            status=status,
            withdrawn_at=None
        )

        db.session.add(new_assignment)
        db.session.flush()

        question_texts = request.form.getlist('question_text[]')
        knowledge_points = request.form.getlist('knowledge_point[]')

        for question_text, knowledge_point in zip(question_texts, knowledge_points):
            if question_text.strip():
                assignment_question = AssignmentQuestion(
                    assignment_id=new_assignment.id,
                    prompt=question_text.strip(),
                    knowledge_point=knowledge_point.strip() or '未指定'
                )
                db.session.add(assignment_question)

        db.session.commit()

        flash('作业已保存' + ('为草稿' if status == 'draft' else '并发布'), 'success')
        return redirect(url_for('teacher_dashboard'))

    return render_template('create_assignment.html', courses=teacher_courses, assignment=None)


@app.route('/teacher/assignment/<int:assignment_id>/edit', methods=['GET', 'POST'])
def edit_assignment(assignment_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    assignment = Assignment.query.get_or_404(assignment_id)

    if assignment.teacher_id != session['user_id']:
        flash('没有权限编辑该作业。', 'error')
        return redirect(url_for('teacher_dashboard'))

    teacher_courses = Course.query.filter_by(teacher_id=session['user_id']).all()

    if request.method == 'POST':
        assignment.title = request.form['title']
        assignment.content = request.form['content']
        due_date_str = request.form['due_date']
        assignment.due_date = datetime.strptime(due_date_str, '%Y-%m-%d') if due_date_str else None
        course_id = request.form.get('course_id')
        assignment.course_id = int(course_id) if course_id else None

        publish_action = request.form.get('publish_action', assignment.status)
        if publish_action == 'draft':
            assignment.status = 'draft'
        elif publish_action == 'withdrawn':
            assignment.status = 'withdrawn'
            assignment.withdrawn_at = datetime.utcnow()
        else:
            assignment.status = 'published'
            assignment.withdrawn_at = None

        # 清理旧的题目
        AssignmentQuestion.query.filter_by(assignment_id=assignment.id).delete(synchronize_session=False)

        question_texts = request.form.getlist('question_text[]')
        knowledge_points = request.form.getlist('knowledge_point[]')

        for question_text, knowledge_point in zip(question_texts, knowledge_points):
            if question_text.strip():
                assignment_question = AssignmentQuestion(
                    assignment_id=assignment.id,
                    prompt=question_text.strip(),
                    knowledge_point=knowledge_point.strip() or '未指定'
                )
                db.session.add(assignment_question)

        db.session.commit()
        flash('作业已更新。', 'success')
        return redirect(url_for('teacher_dashboard'))

    return render_template('create_assignment.html', courses=teacher_courses, assignment=assignment)


@app.route('/teacher/assignment/<int:assignment_id>/withdraw', methods=['POST'])
def withdraw_assignment(assignment_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.teacher_id != session['user_id']:
        flash('没有权限撤回该作业。', 'error')
        return redirect(url_for('teacher_dashboard'))

    assignment.status = 'withdrawn'
    assignment.withdrawn_at = datetime.utcnow()
    db.session.commit()
    flash('作业已撤回，可编辑后重新发布。', 'success')
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/assignment/<int:assignment_id>/publish', methods=['POST'])
def publish_assignment(assignment_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.teacher_id != session['user_id']:
        flash('没有权限操作该作业。', 'error')
        return redirect(url_for('teacher_dashboard'))

    assignment.status = 'published'
    assignment.withdrawn_at = None
    db.session.commit()
    flash('作业已发布。', 'success')
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/courses', methods=['GET', 'POST'])
def manage_courses():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')

        if not name:
            flash('课程名称不能为空。', 'error')
        else:
            invite_code = None
            while not invite_code:
                candidate = generate_invite_code()
                if not Course.query.filter_by(invite_code=candidate).first():
                    invite_code = candidate

            new_course = Course(
                name=name,
                description=description,
                invite_code=invite_code,
                teacher_id=session['user_id']
            )
            db.session.add(new_course)
            db.session.commit()
            flash('课程创建成功。邀请码：' + invite_code, 'success')
            return redirect(url_for('manage_courses'))

    courses = Course.query.filter_by(teacher_id=session['user_id']).order_by(Course.created_at.desc()).all()
    return render_template('course_management.html', courses=courses)


@app.route('/teacher/course/<int:course_id>/delete', methods=['POST'])
def delete_course(course_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    course = Course.query.get_or_404(course_id)
    if course.teacher_id != session['user_id']:
        flash('没有权限解散该课程。', 'error')
        return redirect(url_for('manage_courses'))

    # 删除与该课程相关的作业、提交和选课关系
    try:
        # 删除该课程下的作业及其相关内容
        assignments = Assignment.query.filter_by(course_id=course.id).all()
        for assignment in assignments:
            Submission.query.filter_by(assignment_id=assignment.id).delete(synchronize_session=False)
            AssignmentQuestion.query.filter_by(assignment_id=assignment.id).delete(synchronize_session=False)
            db.session.delete(assignment)

        # 删除课程材料及其文件
        materials = CourseMaterial.query.filter_by(course_id=course.id).all()
        for material in materials:
            if material.file_path and os.path.exists(material.file_path):
                try:
                    os.remove(material.file_path)
                except Exception as e:
                    print(f"删除材料文件失败: {e}")
            db.session.delete(material)

        # 删除选课记录
        CourseEnrollment.query.filter_by(course_id=course.id).delete(synchronize_session=False)

        # 删除课程本身
        db.session.delete(course)
        db.session.commit()
        flash('课程已成功解散。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'解散课程时出错: {str(e)}', 'error')

    return redirect(url_for('manage_courses'))


@app.route('/teacher/course/<int:course_id>/upload_material', methods=['GET', 'POST'])
def upload_course_material(course_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    course = Course.query.get_or_404(course_id)
    if course.teacher_id != session['user_id']:
        flash('没有权限上传该课程的资料。', 'error')
        return redirect(url_for('manage_courses'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        material_type = request.form.get('material_type', '')
        description = request.form.get('description', '').strip()
        file = request.files.get('file')

        if not title:
            flash('请输入资料标题。', 'error')
            materials = CourseMaterial.query.filter_by(course_id=course_id).order_by(
                CourseMaterial.created_at.desc()).all()
            return render_template('upload_material.html', course=course, materials=materials)

        if not material_type:
            flash('请选择资料类型。', 'error')
            materials = CourseMaterial.query.filter_by(course_id=course_id).order_by(
                CourseMaterial.created_at.desc()).all()
            return render_template('upload_material.html', course=course, materials=materials)

        if not file or not file.filename:
            flash('请选择要上传的文件。', 'error')
            materials = CourseMaterial.query.filter_by(course_id=course_id).order_by(
                CourseMaterial.created_at.desc()).all()
            return render_template('upload_material.html', course=course, materials=materials)

        if not allowed_material_file(file.filename):
            flash('不支持的文件类型。', 'error')
            materials = CourseMaterial.query.filter_by(course_id=course_id).order_by(
                CourseMaterial.created_at.desc()).all()
            return render_template('upload_material.html', course=course, materials=materials)

        try:
            # 生成安全的文件名
            filename = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
            unique_filename = f"{timestamp}{filename}"
            file_path = os.path.join(app.config['MATERIAL_FOLDER'], unique_filename)
            file.save(file_path)

            # 获取文件大小
            file_size = os.path.getsize(file_path)

            # 创建课程材料记录
            new_material = CourseMaterial(
                course_id=course_id,
                teacher_id=session['user_id'],
                title=title,
                material_type=material_type,
                file_path=file_path,
                file_name=filename,
                file_size=file_size,
                description=description,
                published=False
            )
            db.session.add(new_material)
            db.session.commit()

            flash('资料上传成功！请点击发布按钮发布资料。', 'success')
            return redirect(url_for('upload_course_material', course_id=course_id))
        except Exception as e:
            db.session.rollback()
            flash(f'上传失败: {str(e)}', 'error')

    materials = CourseMaterial.query.filter_by(course_id=course_id).order_by(CourseMaterial.created_at.desc()).all()
    return render_template('upload_material.html', course=course, materials=materials)


@app.route('/teacher/course/<int:course_id>/publish_material/<int:material_id>', methods=['POST'])
def publish_course_material(course_id, material_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    material = CourseMaterial.query.get_or_404(material_id)
    if material.teacher_id != session['user_id'] or material.course_id != course_id:
        flash('没有权限操作该资料。', 'error')
        return redirect(url_for('manage_courses'))

    material.published = True
    db.session.commit()
    flash('资料已发布！', 'success')
    return redirect(url_for('upload_course_material', course_id=course_id))


@app.route('/student/course/<int:course_id>/leave', methods=['POST'])
def leave_course(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    enrollment = CourseEnrollment.query.filter_by(
        course_id=course_id,
        student_id=session['user_id']
    ).first()

    if not enrollment:
        flash('您尚未加入该课程。', 'error')
        return redirect(url_for('student_dashboard'))

    try:
        db.session.delete(enrollment)
        db.session.commit()
        flash('已成功退出课程。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'退出课程时出错: {str(e)}', 'error')

    return redirect(url_for('student_dashboard'))


@app.route('/student/join_course', methods=['GET', 'POST'])
def join_course():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    if request.method == 'POST':
        invite_code = request.form.get('invite_code', '').upper().strip()

        course = Course.query.filter_by(invite_code=invite_code).first()
        if not course:
            flash('邀请码无效，请检查后再试。', 'error')
        else:
            existing = CourseEnrollment.query.filter_by(course_id=course.id, student_id=session['user_id']).first()
            if existing:
                flash('您已加入该课程。', 'info')
            else:
                enrollment = CourseEnrollment(course_id=course.id, student_id=session['user_id'])
                db.session.add(enrollment)
                db.session.commit()
                flash(f'成功加入课程 {course.name}', 'success')
                return redirect(url_for('student_dashboard'))

    return render_template('student_join_course.html')


@app.route('/teacher/view_submissions/<int:assignment_id>')
def view_submissions(assignment_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    assignment = Assignment.query.get_or_404(assignment_id)

    # 确保老师只能查看自己发布的作业
    if assignment.teacher_id != session['user_id']:
        return redirect(url_for('teacher_dashboard'))

    # 使用正确的关系访问
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    return render_template('view_submissions.html', assignment=assignment, submissions=submissions)


@app.route('/teacher/grade_submission/<int:submission_id>', methods=['POST'])
def grade_submission(submission_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    submission = Submission.query.get_or_404(submission_id)
    assignment = submission.assignment
    
    # 确保老师只能给自己的作业评分
    if assignment.teacher_id != session['user_id']:
        flash('没有权限评分此提交', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    grade = request.form.get('grade', '').strip()
    teacher_comment = request.form.get('teacher_comment', '').strip()
    
    try:
        submission.grade = grade if grade else None
        submission.teacher_comment = teacher_comment if teacher_comment else None
        db.session.commit()
        flash('评分和修改意见已保存', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'保存失败: {str(e)}', 'error')
    
    return redirect(url_for('view_submissions', assignment_id=assignment.id))


@app.route('/student/dashboard')
def student_dashboard():
    # 检查会话
    if 'user_id' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        flash('无权限访问学生面板', 'error')
        return redirect(url_for('login'))

    enrollments = CourseEnrollment.query.filter_by(student_id=session['user_id']).all()
    course_ids = [enrollment.course_id for enrollment in enrollments]
    student_courses = Course.query.filter(Course.id.in_(course_ids)).all() if course_ids else []

    assignments_query = Assignment.query.filter(Assignment.status == 'published')
    if course_ids:
        assignments_query = assignments_query.filter(
            or_(Assignment.course_id.is_(None), Assignment.course_id.in_(course_ids))
        )
    else:
        assignments_query = assignments_query.filter(Assignment.course_id.is_(None))

    assignments = assignments_query.order_by(Assignment.created_at.desc()).all()
    assignments_with_status = []

    for assignment in assignments:
        # 检查学生是否已提交该作业
        submission = Submission.query.filter_by(
            assignment_id=assignment.id,
            student_id=session['user_id']
        ).first()

        assignments_with_status.append({
            'assignment': assignment,
            'submitted': submission is not None,
            'submission': submission
        })

    # 添加调试信息
    print(f"找到 {len(assignments)} 个作业")
    print(
        f"学生 {session['user_id']} 的作业状态: {[(item['assignment'].title, item['submitted']) for item in assignments_with_status]}")

    return render_template('student_dashboard.html',
                           assignments=assignments_with_status,
                           courses=student_courses,
                           has_course=bool(student_courses))


@app.route('/student/profile')
def student_profile():
    if 'user_id' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        flash('无权限访问该页面', 'error')
        return redirect(url_for('login'))

    user = User.query.get_or_404(session['user_id'])

    enrollments = CourseEnrollment.query.filter_by(student_id=user.id).order_by(CourseEnrollment.joined_at.desc()).all()
    courses_info = []
    for enrollment in enrollments:
        course = enrollment.course
        teacher = course.teacher if course else None
        courses_info.append({
            'course': course,
            'teacher': teacher,
            'joined_at': enrollment.joined_at
        })

    masked_password = '*' * len(user.password) if user.password else '未设置'

    return render_template('student_profile.html',
                           user=user,
                           masked_password=masked_password,
                           courses_info=courses_info)


@app.route('/student/change_password', methods=['POST'])
def change_student_password():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get_or_404(session['user_id'])
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not old_password or not new_password or not confirm_password:
        flash('请填写所有字段', 'error')
        return redirect(url_for('student_profile'))
    
    if user.password != old_password:
        flash('原密码错误', 'error')
        return redirect(url_for('student_profile'))
    
    if new_password != confirm_password:
        flash('两次输入的新密码不一致', 'error')
        return redirect(url_for('student_profile'))
    
    if len(new_password) < 6:
        flash('新密码长度至少6个字符', 'error')
        return redirect(url_for('student_profile'))
    
    try:
        user.password = new_password
        db.session.commit()
        flash('密码修改成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'密码修改失败: {str(e)}', 'error')
    
    return redirect(url_for('student_profile'))


@app.route('/student/delete_account', methods=['POST'])
def delete_student_account():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = User.query.get_or_404(user_id)
    
    try:
        # 删除学生的选课记录
        CourseEnrollment.query.filter_by(student_id=user_id).delete(synchronize_session=False)
        
        # 删除学生的提交记录及其文件
        submissions = Submission.query.filter_by(student_id=user_id).all()
        for submission in submissions:
            # 删除上传的文件
            if submission.file_path and os.path.exists(submission.file_path):
                try:
                    os.remove(submission.file_path)
                except Exception as e:
                    print(f"删除文件失败: {e}")
            db.session.delete(submission)
        
        # 删除用户
        db.session.delete(user)
        db.session.commit()
        
        # 清除session
        session.clear()
        flash('账户已成功注销', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        db.session.rollback()
        flash(f'注销账户时出错: {str(e)}', 'error')
        return redirect(url_for('student_profile'))


@app.route('/student/submit_assignment/<int:assignment_id>', methods=['GET', 'POST'])
def submit_assignment(assignment_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    assignment = Assignment.query.get_or_404(assignment_id)

    if assignment.status != 'published':
        flash('该作业目前不可提交，请等待老师重新发布。', 'info')
        return redirect(url_for('student_dashboard'))

    # 检查是否已提交
    existing_submission = Submission.query.filter_by(
        assignment_id=assignment_id,
        student_id=session['user_id']
    ).first()

    if request.method == 'POST':
        content = request.form.get('content', '')
        file = request.files.get('file')

        # 处理文件上传
        file_path = None
        file_name = None

        if file and file.filename:
            if allowed_file(file.filename):
                # 生成安全的文件名
                filename = secure_filename(file.filename)
                # 添加时间戳避免重名
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
                unique_filename = f"{timestamp}{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                file_name = filename
                flash('文件上传成功!', 'success')
            else:
                flash('不支持的文件类型。请上传 txt, pdf, doc 或 docx 文件。', 'error')
                return render_template('submit_assignment.html',
                                       assignment=assignment,
                                       submission=existing_submission)

        try:
            if existing_submission:
                # 更新现有提交
                existing_submission.content = content
                if file_path:
                    # 如果之前有文件，删除旧文件
                    if existing_submission.file_path and os.path.exists(existing_submission.file_path):
                        os.remove(existing_submission.file_path)
                    existing_submission.file_path = file_path
                    existing_submission.file_name = file_name
                existing_submission.submitted_at = datetime.utcnow()
                message = '作业提交已更新!'
            else:
                # 创建新提交
                new_submission = Submission(
                    assignment_id=assignment_id,
                    student_id=session['user_id'],
                    content=content,
                    file_path=file_path,
                    file_name=file_name
                )
                db.session.add(new_submission)
                message = '作业提交成功!'

            db.session.commit()
            flash(message, 'success')
            return redirect(url_for('student_dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'提交错误: {str(e)}', 'error')

    return render_template('submit_assignment.html',
                           assignment=assignment,
                           submission=existing_submission)


# 注册路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    # 如果是老师登录，重定向到教师面板
    if 'user_id' in session and session['role'] == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    # 如果是学生登录，重定向到学生面板
    elif 'user_id' in session and session['role'] == 'student':
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        name = request.form['name']
        role = request.form.get('role', 'student')  # 默认为学生
        email = request.form.get('email', '')

        # 验证输入
        if not username or not password or not confirm_password or not name:
            flash('请填写所有必填字段', 'error')
            return render_template('register.html', selected_role=role)

        if password != confirm_password:
            flash('密码确认不匹配', 'error')
            return render_template('register.html', selected_role=role)

        # 验证角色
        if role not in ['student', 'teacher']:
            flash('无效的角色选择', 'error')
            return render_template('register.html', selected_role='student')

        # 检查用户名是否已存在
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('用户名已存在，请选择其他用户名', 'error')
            return render_template('register.html', selected_role=role)

        # 创建新用户
        new_user = User(
            username=username,
            password=password,
            role=role,
            name=name,
            email=email if email else None
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            role_name = '教师' if role == 'teacher' else '学生'
            flash(f'{role_name}账号注册成功！请登录', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('注册失败，请稍后重试', 'error')
            return render_template('register.html', selected_role=role)

    # 默认显示学生注册
    selected_role = request.args.get('role', 'student')
    return render_template('register.html', selected_role=selected_role)


@app.route('/teacher/student_management')
def student_management():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    # 获取所有学生，包括他们的提交信息
    students = User.query.filter_by(role='student').all()
    return render_template('student_management.html', students=students)



@app.route('/download/<int:submission_id>')
def download_file(submission_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    submission = Submission.query.get_or_404(submission_id)

    # 权限检查：老师可以下载任何提交，学生只能下载自己的提交
    if session['role'] == 'student' and submission.student_id != session['user_id']:
        flash('没有权限访问此文件', 'error')
        return redirect(url_for('student_dashboard'))

    if not submission.file_path or not os.path.exists(submission.file_path):
        flash('文件不存在', 'error')
        return redirect(request.referrer or url_for('student_dashboard'))

    # 发送文件
    return send_file(
        submission.file_path,
        as_attachment=True,
        download_name=submission.file_name or f"submission_{submission_id}.docx"
    )


# 添加学习计划
@app.route('/preview/<int:submission_id>')
def preview_file(submission_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    submission = Submission.query.get_or_404(submission_id)

    # 权限检查
    if session['role'] == 'student' and submission.student_id != session['user_id']:
        flash('没有权限访问此文件', 'error')
        return redirect(url_for('student_dashboard'))

    if not submission.file_path or not os.path.exists(submission.file_path):
        flash('文件不存在', 'error')
        return redirect(request.referrer or url_for('student_dashboard'))

    # 初始化学习计划相关变量
    study_plan = None
    plan_status = "未生成"

    # 尝试读取Word文档内容
    try:
        if submission.file_path.endswith('.docx'):
            doc = Document(submission.file_path)
            content = ""
            for paragraph in doc.paragraphs:
                content += paragraph.text + "\n"

            grader_result = None
            if Config.IS_LLM_RUN:
                # 如果还没有AI评分结果，则生成并保存
                if not submission.evaluation_result:
                    try:
                        # 创建判分器实例
                        grader = PythonCodeGrader()
                        grader_result = grader.evaluate_code_2(content)
                        print(f"📊作业评估结果，来自大模型{Config.MODEL_NAME}--->\n", grader_result)

                        # 保存评分结果到数据库
                        submission.evaluation_result = grader_result

                        # 尝试从评分结果中提取分数
                        score_match = re.search(r'(\d+(?:\.\d+)?)\s*分', grader_result)
                        if not score_match:
                            score_match = re.search(r'分数[：:]\s*(\d+(?:\.\d+)?)', grader_result)
                        if not score_match:
                            score_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*100', grader_result)
                        if not score_match:
                            score_match = re.search(r'(\d+(?:\.\d+)?)\s*%', grader_result)

                        if score_match:
                            try:
                                submission.ai_score = float(score_match.group(1))
                            except:
                                pass

                        db.session.commit()
                    except ValueError as e:
                        print(f"❌ 初始化错误：{e}")
                    except Exception as e:
                        print(f"❌ 运行错误：{e}")
                else:
                    grader_result = submission.evaluation_result

                #同步生成学习计划
                if grader_result:  # 有评分结果则同步生成学习计划
                    plan_status = "生成中..."
                    try:
                        # 创建判分器实例
                        grader = PythonCodeGrader()
                        # 同步调用学习计划生成方法（无异步线程）
                        study_plan = grader.generate_study_plan(
                            homework_content=content,
                            evaluation_result=grader_result
                        )
                        plan_status = "生成成功"
                        print(f"✅ 作业{submission_id}学习计划生成完成：\n{study_plan[:100]}...")
                    except Exception as e:
                        plan_status = f"生成失败：{str(e)[:20]}"
                        study_plan = None
                        print(f"❌ 学习计划生成失败：{str(e)}")
                #

            else:
                grader_result = submission.evaluation_result

            if Config.IS_SOUND_ON and grader_result:
                assistant = VoiceAssistant()
                assistant.speak(grader_result)

            #
            return render_template('file_preview.html',
                                   submission=submission,
                                   file_content=content,
                                   grader_result=grader_result,
                                   file_type='Word文档',
                                   study_plan=study_plan,
                                   plan_status=plan_status)
        else:

            return render_template('file_preview.html',
                                   submission=submission,
                                   content="此文件类型不支持在线预览，请下载查看。",
                                   file_type=submission.file_name.split('.')[-1].upper() if submission.file_name else '未知',
                                   study_plan=None,
                                   plan_status="不支持生成")

    except Exception as e:
        # 异常场景
        return render_template('file_preview.html',
                               submission=submission,
                               content=f"文件读取错误: {str(e)}",
                               file_type='错误',
                               study_plan=None,
                               plan_status="生成失败")


@app.route('/student/course/<int:course_id>/materials')
def view_course_materials(course_id):
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    # 检查学生是否已加入该课程
    enrollment = CourseEnrollment.query.filter_by(
    course_id = course_id,
    student_id = session['user_id']
    ).first()

    if not enrollment:
        flash('您尚未加入该课程。', 'error')
        return redirect(url_for('student_dashboard'))

    course = Course.query.get_or_404(course_id)
    # 只显示已发布的资料
    materials = CourseMaterial.query.filter_by(
        course_id=course_id,
        published=True
    ).order_by(CourseMaterial.created_at.desc()).all()

    return render_template('view_materials.html', course=course, materials=materials)


@app.route('/download_material/<int:material_id>')
def download_material(material_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    material = CourseMaterial.query.get_or_404(material_id)

    # 权限检查
    if session['role'] == 'teacher':
        # 教师只能下载自己上传的资料
        if material.teacher_id != session['user_id']:
            flash('没有权限访问此文件', 'error')
            return redirect(url_for('teacher_dashboard'))
    elif session['role'] == 'student':
        # 学生只能下载已发布且已加入课程的资料
        if not material.published:
            flash('该资料尚未发布', 'error')
            return redirect(url_for('student_dashboard'))
        enrollment = CourseEnrollment.query.filter_by(
            course_id=material.course_id,
            student_id=session['user_id']
        ).first()
        if not enrollment:
            flash('您尚未加入该课程', 'error')
            return redirect(url_for('student_dashboard'))

    if not material.file_path or not os.path.exists(material.file_path):
        flash('文件不存在', 'error')
        return redirect(request.referrer or url_for('student_dashboard'))

    # 发送文件
    return send_file(
        material.file_path,
        as_attachment=True,
        download_name=material.file_name
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)