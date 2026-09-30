FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ gdb libstdc++6 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 10001 runner
WORKDIR /app
COPY server.py gdb_trace.py ./
USER runner
ENV PORT=8080
EXPOSE 8080
CMD ["python", "server.py"]
