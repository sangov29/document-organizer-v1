FROM mcr.microsoft.com/playwright:v1.63.0-noble
WORKDIR /tests
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
CMD ["npm", "test"]
