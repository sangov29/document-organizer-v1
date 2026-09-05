FROM mcr.microsoft.com/playwright:v1.51.1-noble
WORKDIR /tests
COPY package.json ./
RUN npm install
COPY . ./
CMD ["npm", "test"]
