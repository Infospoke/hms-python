from typing import Generator
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select
from app.db.session import get_session
from app import models
from app.core import config as consts
