import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'aP3tr&glsfjsf8O!dfL%0PmZs2erA#9xR!jWq') 
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/ecommerce_db')
