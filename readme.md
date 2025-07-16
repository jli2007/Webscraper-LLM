# Webscraper LLM Cloner
#### web scraper (fast api, browserbase) --> llm (openai) --> client (nextjs).

###### essentially scrapes a website for data, sends it to openai (yes, claude would be more optimal) and asks it to generate a website based on the information gathered.

note: works well with basic/classic websites, not so well with modern ones. focusing on other things rn, *will perhaps optimize later* 

(i probably won't)

https://github.com/user-attachments/assets/e16b11d6-ede5-43c6-9b3d-1e88a36f1bc6

## Backend

The backend uses `uv` for package management.

### Installation

To install the backend dependencies, run the following command in the backend project directory:

```bash
uv sync
```

### Running the Backend

To run the backend development server, use the following command:

```bash
uv run fastapi dev
```

## Frontend

The frontend is built with Next.js and TypeScript.

### Installation

To install the frontend dependencies, navigate to the frontend project directory and run:

```bash
npm install
```

### Running the Frontend

To start the frontend development server, run:

```bash
npm run dev
```
