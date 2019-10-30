FROM python:3.7.3-slim

COPY . /app
WORKDIR /app

RUN ["chmod", "+x", "stdf2xml"]

