from importlib import import_module

from app.main import app, db

import_module("app.main")
import_module("app.views")
import_module("app.recipes.models")
import_module("app.recipes.views")

db.create_all()
