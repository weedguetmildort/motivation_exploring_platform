# Use official Node image
FROM node:20

# Set working directory inside container
WORKDIR /app

# Copy package.json and package-lock.json first
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the frontend code
COPY . .

# Expose port for Next.js
EXPOSE 3000

# Run Next.js in dev mode (you can change to `npm run build && npm start` for prod)
CMD ["npm", "run", "dev"]
