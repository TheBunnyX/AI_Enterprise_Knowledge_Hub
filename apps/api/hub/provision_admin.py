"""One-time admin provisioning after migrations; password read securely from terminal."""
import getpass
from sqlalchemy import select
from .database import SessionLocal
from .models import User, Organization
from .auth import passwords

def main():
    email=input('Administrator email: ').strip().lower()
    name=input('Administrator display name: ').strip()
    organization=input('Organization name: ').strip()
    password=getpass.getpass('Administrator password (min 16 chars): ')
    if '@' not in email or not name or not organization or len(password)<16: raise SystemExit('Invalid input')
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.role=='SUPER_ADMIN')): raise SystemExit('An administrator already exists. Use authorized administration.')
        o=Organization(name=organization,plan='Enterprise');db.add(o);db.flush()
        db.add(User(tenant_id=o.id,email=email,name=name,role='SUPER_ADMIN',password_hash=passwords.hash(password)));db.commit()
    print('Administrator provisioned. Configure the same verified email in your Identity Provider.')
if __name__=='__main__': main()
