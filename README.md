# Stock Data API

This is a backend web application that provides real-time stock data. It's built with Python and FastAPI.

## Setup

1.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
2.  Create a `.env` file in the root of the project and add your API keys:
    ```
    FINNHUB_API_KEY="your_finnhub_api_key"
    POLYGON_API_KEY="your_polygon_api_key"
    ```

## Running the Application

To start the web server, run the following command:

```bash
python main.py
```

The application will be available at `http://localhost:8000`.

## API Endpoints

The following endpoints are available:

### Get Stock Data

*   **URL:** `/data`
*   **Method:** `GET`
*   **Description:** Fetches and returns the latest stock data in JSON format for the configured tickers.

### Update Symbols

*   **URL:** `/symbols`
*   **Method:** `POST`
*   **Description:** Updates the list of stock symbols to monitor.
*   **Request Body:** A JSON array of strings.
*   **Example:**
    ```json
    [
        "AAPL",
        "GOOG",
        "MSFT"
    ]
    ```

### Reset Cache

*   **URL:** `/cache/reset`
*   **Method:** `POST`
*   **Description:** Clears the in-memory cache of the application.
