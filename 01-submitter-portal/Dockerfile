FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev --fetch-retries=5 --fetch-timeout=120000 --no-audit --no-fund && test -s node_modules/next/package.json

COPY . .
COPY package.json ./
RUN test -s package.json && npm run build
RUN node -e "require('node:fs').writeFileSync('package.json', JSON.stringify({name:'computetorrent-portal',version:'1.0.0',private:true}))"

EXPOSE 3000

CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "3000"]
