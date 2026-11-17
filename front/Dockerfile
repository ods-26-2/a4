FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# o navegador chama o back por este endereco, gravado no build
ARG NEXT_PUBLIC_API_URL
RUN npm run build
CMD ["npm", "start"]
