# Deployment Guide

This guide covers deploying Job Finder to production.

## Pre-Deployment Checklist

Run the production readiness check:

```bash
./production_check.sh
```

Ensure all critical checks pass before deploying.

## Environment Configuration

### Required Environment Variables

```bash
DATABASE_URL=postgresql://user:password@host:port/database
GEMINI_API_KEY=your_production_api_key
FLASK_SECRET_KEY=generate_strong_random_key_32_bytes
FLASK_DEBUG=false
PORT=5000
LOG_LEVEL=INFO
```

### Generate Secure Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Deployment Options

### Option 1: Traditional Server (Linux)

1. **Install Dependencies**
   ```bash
   sudo apt update
   sudo apt install python3-pip postgresql nginx
   pip install -r requirements.txt
   playwright install --with-deps chromium
   ```

2. **Set Up PostgreSQL**
   ```bash
   sudo -u postgres createdb jobfinder
   sudo -u postgres psql -d jobfinder -f database/schema.sql
   ```

3. **Configure Systemd Service**
   Create `/etc/systemd/system/jobfinder.service`:
   ```ini
   [Unit]
   Description=Job Finder Web Application
   After=network.target postgresql.service

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/opt/jobfinder
   Environment="PATH=/opt/jobfinder/venv/bin"
   EnvironmentFile=/opt/jobfinder/.env
   ExecStart=/opt/jobfinder/venv/bin/python web/app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

4. **Start Service**
   ```bash
   sudo systemctl enable jobfinder
   sudo systemctl start jobfinder
   ```

5. **Configure Nginx**
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Option 2: Docker

1. **Create Dockerfile**
   ```dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   
   RUN apt-get update && apt-get install -y \
       postgresql-client \
       && rm -rf /var/lib/apt/lists/*
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   RUN playwright install --with-deps chromium
   
   COPY . .
   
   ENV FLASK_DEBUG=false
   
   EXPOSE 5000
   
   CMD ["python", "web/app.py"]
   ```

2. **Create docker-compose.yml**
   ```yaml
   version: '3.8'
   
   services:
     web:
       build: .
       ports:
         - "5000:5000"
       environment:
         - DATABASE_URL=postgresql://jobfinder:password@db:5432/jobfinder
         - GEMINI_API_KEY=${GEMINI_API_KEY}
         - FLASK_SECRET_KEY=${FLASK_SECRET_KEY}
       depends_on:
         - db
     
     db:
       image: postgres:15
       environment:
         - POSTGRES_DB=jobfinder
         - POSTGRES_USER=jobfinder
         - POSTGRES_PASSWORD=password
       volumes:
         - pgdata:/var/lib/postgresql/data
         - ./database/schema.sql:/docker-entrypoint-initdb.d/schema.sql
   
   volumes:
     pgdata:
   ```

3. **Deploy**
   ```bash
   docker-compose up -d
   ```

### Option 3: Cloud Platform (Heroku)

1. **Create `Procfile`**
   ```
   web: python web/app.py
   ```

2. **Create `runtime.txt`**
   ```
   python-3.11
   ```

3. **Deploy**
   ```bash
   heroku create your-app-name
   heroku addons:create heroku-postgresql:hobby-dev
   heroku config:set GEMINI_API_KEY=your_key
   heroku config:set FLASK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
   git push heroku main
   heroku run psql 
 $DATABASE_URL -f database/schema.sql
   ```

## Post-Deployment

### Verify Deployment

1. **Health Check**
   ```bash
   curl https://yourdomain.com/api/health
   ```

2. **Database Connection**
   ```bash
   psql $DATABASE_URL -c "SELECT count(*) FROM companies;"
   ```

3. **Logs**
   ```bash
   # Systemd
   journalctl -u jobfinder -f
   
   # Docker
   docker-compose logs -f
   
   # Heroku
   heroku logs --tail
   ```

### Monitoring

- Set up logging aggregation (e.g., Papertrail, Loggly)
- Monitor database performance
- Track API response times
- Set up alerts for errors

### Backups

```bash
# Database backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Restore
psql $DATABASE_URL < backup_20250101.sql
```

## Security

- Use HTTPS (Let's Encrypt with Certbot)
- Keep dependencies updated: `pip install --upgrade -r requirements.txt`
- Rotate API keys regularly
- Monitor for suspicious activity
- Use environment variables for secrets
- Enable database connection encryption
- Implement rate limiting

## Scaling

### Horizontal Scaling

- Run multiple web instances behind load balancer
- Use shared PostgreSQL instance
- Consider Redis for session storage

### Performance Optimization

- Enable database query caching
- Use CDN for static assets
- Implement request caching
- Optimize Playwright scraping (parallel execution)

## Troubleshooting

### High Memory Usage
- Playwright browsers can use significant memory
- Limit concurrent scraping operations
- Restart workers periodically

### Slow Database Queries
- Add indexes to frequently queried columns
- Analyze query performance: `EXPLAIN ANALYZE`
- Consider connection pooling

### Playwright Crashes
- Ensure sufficient memory (2GB+ recommended)
- Update Playwright: `playwright install --force chromium`
- Check system dependencies

## Rollback

```bash
# Systemd
sudo systemctl stop jobfinder
cd /opt/jobfinder
git checkout previous-version
sudo systemctl start jobfinder

# Docker
docker-compose down
git checkout previous-version
docker-compose up -d

# Heroku
heroku releases
heroku rollback v123
```

## Support

For deployment issues, check:
- Application logs
- Database connectivity
- Environment variables
- File permissions
- Network/firewall settings
