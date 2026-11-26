"""Doctor applications are separate from active staff accounts until reviewed."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import database as db
from .auth import hash_password
from .auth_service import _user_id, login_rate_limited, record_login_failure
from .admin_api import _admin
from .clinical_api import _user, _ip

router = APIRouter(prefix='/api', tags=['doctor registration'])


class DoctorApplication(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=40, pattern=r'^[a-zA-Z0-9_.-]+$')
    display_name: str = Field(min_length=2, max_length=60)
    institution: str = Field(min_length=2, max_length=120)
    department: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=12, max_length=128)

    @field_validator('username', 'display_name', 'institution', 'department', mode='before')
    @classmethod
    def trim_profile(cls, value):
        return value.strip() if isinstance(value, str) else value


class ApplicationReview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision: Literal['approved', 'rejected']
    reason: str = Field(default='', max_length=500)


@router.post('/auth/register', status_code=202)
def register(req: DoctorApplication, request: Request):
    # IP-wide quota also limits attempts made with different account names.
    key = 'doctor-registration|' + (_ip(request) or 'unknown')
    if login_rate_limited(key):
        raise HTTPException(429, '申请过于频繁，请 15 分钟后再试')
    record_login_failure(key)
    password_hash = hash_password(req.password)
    with db.transaction(immediate=True) as conn:
        exists = conn.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE', (req.username,)).fetchone()
        application = conn.execute('SELECT 1 FROM doctor_applications WHERE username=? COLLATE NOCASE', (req.username,)).fetchone()
        # Same response for existing accounts/applications; never reset a pending password.
        if not exists and not application:
            conn.execute('''INSERT INTO doctor_applications
                (id,username,display_name,institution,department,password_hash,created_at)
                VALUES(?,?,?,?,?,?,?)''',
                (db.new_id('REG'), req.username, req.display_name, req.institution,
                 req.department, password_hash, db.utc_now()))
    return {'message': '申请已受理。如账号符合申请条件，管理员审核通过后即可登录；如需查询审核结果，请联系管理员。'}


@router.get('/admin/doctor-applications')
def applications(request: Request):
    _admin(_user(request))
    with db.reader() as conn:
        rows = conn.execute('''SELECT id,username,display_name,institution,department,status,
            reason,created_at,reviewed_at FROM doctor_applications
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,created_at DESC''').fetchall()
    return {'applications': [dict(row) for row in rows]}


@router.post('/admin/doctor-applications/{application_id}/review')
def review(application_id: str, req: ApplicationReview, request: Request):
    actor = _user(request)
    _admin(actor)
    if req.decision == 'rejected' and not req.reason:
        raise HTTPException(422, '请填写未通过原因')
    with db.transaction(immediate=True) as conn:
        row = conn.execute('SELECT * FROM doctor_applications WHERE id=?', (application_id,)).fetchone()
        if row is None:
            raise HTTPException(404, '申请不存在')
        if row['status'] != 'pending':
            raise HTTPException(409, '该申请已审核，请刷新列表')
        now = db.utc_now()
        if req.decision == 'approved':
            if conn.execute('SELECT 1 FROM users WHERE username=? COLLATE NOCASE', (row['username'],)).fetchone():
                raise HTTPException(409, '账号已存在，请先核实员工账号')
            conn.execute('''INSERT INTO users
                (id,username,display_name,role,password_hash,active,must_change_password,created_at,updated_at)
                VALUES(?,?,?,'doctor',?,1,0,?,?)''',
                (_user_id(row['username']), row['username'], row['display_name'], row['password_hash'], now, now))
        conn.execute('''UPDATE doctor_applications SET status=?,reason=?,reviewed_at=?,reviewer_id=?,
            password_hash=NULL WHERE id=?''', (req.decision, req.reason, now, actor['id'], application_id))
        db.record_audit(conn, actor_type='user', actor_id=actor['id'], action='doctor_registration_review',
            entity_type='doctor_application', entity_id=application_id,
            detail={'decision': req.decision, 'reason': req.reason}, ip=_ip(request))
    return {'ok': True}
