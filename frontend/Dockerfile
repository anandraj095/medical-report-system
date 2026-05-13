FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Expose Vite's default port
EXPOSE 5173

# Run Vite with --host so it's accessible outside the container
CMD ["npm", "run", "dev", "--", "--host"]