# Dockerfile
FROM mcr.microsoft.com/playwright:v1.60.0-noble

# Recommended Playwright Docker flags are added at runtime (see docker-compose). [web:23]
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install --omit=dev

# Copy app code
COPY scraper.js .

# Non-root user for scraping (already exists in image) [web:23]
USER pwuser

EXPOSE 8080

CMD ["node", "scraper.js"]
