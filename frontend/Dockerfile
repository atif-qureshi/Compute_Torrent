FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev --fetch-retries=10 --fetch-timeout=300000

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
