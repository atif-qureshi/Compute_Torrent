FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --fetch-retries=10 --fetch-timeout=300000
COPY src/ ./src/
ENV SWARM_DATA_DIR=/data PORT=4001
EXPOSE 4001
CMD ["node", "src/swarm_service.js"]
