# syntax=docker/dockerfile:1.7

FROM oven/bun:1.2.20-debian AS application

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

WORKDIR /app

COPY package.json bun.lock ./
COPY analytics/requirements.txt analytics/requirements.txt
RUN bun install --frozen-lockfile \
    && pip install --no-cache-dir -r analytics/requirements.txt \
    && python -c "import duckdb; connection = duckdb.connect(); connection.execute('install postgres'); connection.close()"

COPY . .

EXPOSE 8000
CMD ["python", "scripts/run_api.py"]

FROM oven/bun:1.2.20-debian AS dashboard-build

WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json ./
COPY public public
COPY src src
RUN VITE_DATA_MODE=api bunx vite build

FROM nginx:1.27.5-alpine AS dashboard

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=dashboard-build /app/dist /usr/share/nginx/html

EXPOSE 8080
