FROM python:3.12-slim
WORKDIR /app
COPY bank.py server.py ./
COPY web ./web
ENV PORT=8080
ENV WRONG_QUESTION_BANK_DIR=/data
RUN mkdir -p /data
EXPOSE 8080
CMD ["python", "-u", "server.py"]
