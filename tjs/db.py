# from sqlalchemy import Column, Integer, String, ForeignKey, Table

# from sqlalchemy.orm import relationship, backref

# from sqlalchemy.ext.declarative import declarative_base

# Base = declarative_base()

# class TaskIssue(Base):

#     __tablename__ = "taskissue"

#     taskid = Column(Integer, primary_key=True)

#     first_name = Column(String)

#     last_name = Column(String)

#     books = relationship("Book", backref=backref("author"))
