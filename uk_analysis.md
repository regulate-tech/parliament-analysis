# Parliamentary Speech Analysis with Ollama

This script analyzes parliamentary speeches, leveraging the Ollama API for a two-stage (initial and refined) analysis, stores the results in a SQLite database, and generates a detailed Markdown report. It also logs the processing times for each analysis.

## Features

* **Speech Analysis:** Processes speech texts from a SQLite database.
* **Two-Stage Ollama Analysis:** Performs an initial broad analysis and then refines it into actionable insights using configurable Ollama models.
* **Configurable Prompts:** The prompts sent to Ollama for both analysis stages are fully customizable via the configuration file.
* **Flexible Analysis Scope:** Easily control the number of members to be analyzed.
* **Markdown Reporting:** Generates a human-readable Markdown file summarizing the analyses for each processed member.
* **SQLite Integration:** Reads speech data from one SQLite database and stores analysis results in another, dedicated database.
* **Detailed Logging:** Records start/end times for each analysis stage, member details, and speech size to a CSV log file.

## Prerequisites

Before running the script, ensure you have the following:

1.  **Python 3.x:** The script is written in Python 3.
2.  **Ollama Server:** You must have the Ollama server running locally (or accessible at the configured `OLLAMA_API_URL`).
3.  **Ollama Models:** The Ollama server should have the models specified in your `analysis.cfg` (e.g., `Gemma3`) downloaded and available.
4.  **Source Database:** A SQLite database named `uk/politician_speeches.db` (or whatever path you configure for `SOURCE_DATABASE_NAME`) containing a table named `speeches` with at least `iid`, `name`, `party`, and `speech_text` columns.

## Setup & Running

It's highly recommended to use a virtual environment to manage Python dependencies.

1.  **Create a Python Virtual Environment (recommended):**

    Using `venv`:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

    Using `pipenv`:
    ```bash
    pipenv install
    pipenv shell
    ```

2.  **Install Python Dependencies:**

    Install the required Python libraries using pip:
    ```bash
    pip install requests
    # sqlite3 and configparser are part of Python's standard library
    ```

3.  **Set up Ollama:**

    Ensure your Ollama server is running. You can typically start it via `ollama serve`.
    Download the required models (e.g., Gemma3):
    ```bash
    ollama run Gemma3
    # This will download the model if it's not already present.
    ```

4.  **Prepare your Source Database:**

    Make sure your `uk/politician_speeches.db` (or custom path) is in place and contains the necessary speech data.

5.  **Configure `analysis.cfg`:**

    Create or update the `analysis.cfg` file in the same directory as the script. This file controls all the configurable aspects of the analysis.

    ```ini
    [Database]
    SOURCE_DATABASE_NAME = uk/politician_speeches.db
    ANALYSIS_DATABASE_NAME = ollama_analysis_results.db

    [Ollama]
    OLLAMA_API_URL = http://localhost:11434/api/generate
    OLLAMA_MODEL_NAME = Gemma3
    OLLAMA_REQUEST_TIMEOUT = 180
    OLLAMA_REFINER_MODEL_NAME = Gemma3
    OLLAMA_REFINER_REQUEST_TIMEOUT = 180

    [Output]
    MD_ANALYSIS_FILENAME_TEMPLATE = Parliament_Analysis_Ollama_{num_members}_{date_from}_to_{date_to}.md

    [AnalysisLimits]
    NUMBER_OF_MEMBERS_TO_ANALYZE = 2

    [Prompts.InitialAnalysis]
    template = You are an AI assistant specializing in analyzing political texts.
        Analyze the following collected speeches from the Member of Parliament {member_name}.
        Focus on identifying:
        1.  Main topics addressed (provide a list of max 5-7 key topics).
        2.  General sentiment (e.g., positive, negative, neutral, mixed) with a brief justification.
        3.  The member's argumentative style (e.g., logical, emotional, fact-based, rhetorical, anecdotal, etc.) with examples if possible.
        4.  Key arguments and possible ways to approach this parliamentarian.
        Provide a concise summary of your analysis in bullet points or short paragraphs.

        Format all of this in Markdown. Make it as robust as possible.

        Speeches:
        ---
        {speeches_text}
        ---
        Your analysis:

    [Prompts.RefinementAnalysis]
    template = You are an expert political strategist AI. Your task is to refine an existing analysis of parliamentarian {member_name}.
        The goal is to transform the initial analysis into a version that is highly succinct and sharply focused on actionable insights for someone interested in effectively working with or lobbying this politician.

        INITIAL ANALYSIS TO REFINE:
        ---
        {initial_analysis_text}
        ---

        Rewrite and replace the initial analysis. Your new, refined output must be:
        1.  **Succinct:** Eliminate all non-essential information. Be direct and to the point. Use concise language.
        2.  **Actionable:** For each key observation (e.g., topics, sentiment, argumentative style), explicitly state the implications or concrete strategies for engagement. For instance, if the politician is 'fact-based', an actionable insight would be: "Strategy: Engage using well-researched data and concrete evidence; emotional appeals are likely to be less effective."
        3.  **Focused:** Prioritize the top 2-3 most critical insights that directly inform engagement strategies. What must someone absolutely know to successfully interact with this MP?
        4.  **Clear Structure:** Present the refined analysis in a clear, easily digestible format, preferably using bullet points under key headings. The final output must be in English.
        5.  **Engaging:** Ensure the refined analysis is tailored to practical engagement scenarios, providing clear recommendations for interaction based on the insights.

        Do not offer a critique of the initial analysis itself; instead, directly provide the improved, refined analysis as the output.
        Use Markdown level headings consistently to make the reports clear and well-structured.

        REFINED AND ACTIONABLE ANALYSIS of {member_name}:

    [Logging]
    LOG_FILE_NAME = ollama_analysis_log.csv
    ```
    **Important Note on Multiline Prompts:** For the `template` values under `[Prompts.InitialAnalysis]` and `[Prompts.RefinementAnalysis]`, ensure that all lines after the first one are consistently indented (e.g., by 4 spaces or a tab). This is crucial for `configparser` to correctly read them as a single multiline string.

6.  **Run the Script:**

    Execute the Python script from your terminal:
    ```bash
    python uk_analysis_en_md.py
    ```

## Configuration Options Explained (`analysis.cfg`)

Here's a breakdown of the settings you can adjust in `analysis.cfg`:

### `[Database]`

* **`SOURCE_DATABASE_NAME`**: Path to the SQLite database containing the raw parliamentary speech data.
* **`ANALYSIS_DATABASE_NAME`**: Path to the SQLite database where the Ollama analysis results will be stored. This database will be created if it doesn't exist.

### `[Ollama]`

* **`OLLAMA_API_URL`**: The endpoint for your Ollama API server (e.g., `http://localhost:11434/api/generate`).
* **`OLLAMA_MODEL_NAME`**: The name of the Ollama model to use for the *initial* analysis (e.g., "llama3", "gemma:7b"). Ensure this model is available on your Ollama server.
* **`OLLAMA_REQUEST_TIMEOUT`**: The maximum time in seconds to wait for a response from Ollama during the initial analysis.
* **`OLLAMA_REFINER_MODEL_NAME`**: The name of the Ollama model to use for *refining* the initial analysis. Can be the same as `OLLAMA_MODEL_NAME` or a different one.
* **`OLLAMA_REFINER_REQUEST_TIMEOUT`**: The maximum time in seconds to wait for a response from Ollama during the refinement stage.

### `[Output]`

* **`MD_ANALYSIS_FILENAME_TEMPLATE`**: The template for the generated Markdown report filename.
    * `{num_members}` will be replaced by the actual number of members analyzed in that report.
    * `{date_from}` and `{date_to}` will be replaced by the analysis date range (currently, `date_to` is current date and `date_from` is 365 days prior).

### `[AnalysisLimits]`

* **`NUMBER_OF_MEMBERS_TO_ANALYZE`**: An integer specifying how many members (from the top of the `speeches` table ordered by `iid`) the script should analyze. Useful for testing or partial runs.

### `[Prompts.InitialAnalysis]`

* **`template`**: The multiline string defining the full prompt sent to Ollama for the initial analysis.
    * `{member_name}`: Placeholder for the parliament member's name.
    * `{speeches_text}`: Placeholder for the combined speech text of the member.

### `[Prompts.RefinementAnalysis]`

* **`template`**: The multiline string defining the full prompt sent to Ollama for refining the initial analysis.
    * `{member_name}`: Placeholder for the parliament member's name.
    * `{initial_analysis_text}`: Placeholder for the raw initial analysis output from Ollama.

### `[Logging]`

* **`LOG_FILE_NAME`**: The filename for the CSV log file that records analysis timings and details for each member. A header will be added automatically on the first run if the file doesn't exist.

## Output Files

Upon successful execution, the script will generate/update the following files:

* **`Parliament_Analysis_Ollama_XMembers_YYYY-MM-DD_to_YYYY-MM-DD.md`**: (Example filename) A Markdown report containing the initial and refined analyses for the processed members. The `X` will be the number of members analyzed.
* **`ollama_analysis_results.db`**: A SQLite database storing the structured analysis results (member IID, name, party, initial analysis text, refined analysis text, last analyzed date).
* **`ollama_analysis_log.csv`**: A CSV file with a timestamped record of each member's analysis, including speech size and the start/end datetimes for both initial and refined analysis stages.

## Troubleshooting

* **`Error reading configuration file 'analysis.cfg': Source contains parsing errors`**:
    * Ensure all continuation lines for multiline prompt templates (`template` under `[Prompts.InitialAnalysis]` and `[Prompts.RefinementAnalysis]`) are consistently indented. Do not use outer triple quotes (`"""`) around the value; indentation is sufficient.
* **`Connection Error: Check if Ollama is running and accessible...`**:
    * Verify that your Ollama server is running (e.g., `ollama serve`).
    * Check if the `OLLAMA_API_URL` in `analysis.cfg` is correct.
* **`Timeout: Ollama API did not respond in time...`**:
    * The Ollama model might be slow to respond. Increase `OLLAMA_REQUEST_TIMEOUT` and/or `OLLAMA_REFINER_REQUEST_TIMEOUT` in `analysis.cfg`.
    * Ensure the specified Ollama models are fully downloaded and ready.
* **`No members found in source database` or `Database error`**:
    * Verify `SOURCE_DATABASE_NAME` in `analysis.cfg` is correct and the database exists.
    * Ensure the `speeches` table exists in your source database and contains data.
