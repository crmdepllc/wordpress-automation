# Frontend image — Next.js dashboard (dev server for the Sprint 1 dev env).
FROM node:22-alpine

WORKDIR /app

# Install deps first (cached unless the lockfile changes).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
