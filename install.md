# BT396 Backtester Framework

BT396 is the **Backtest Framework** for COMP396.  
It is built on [Backtrader](https://www.backtrader.com/) and provides a controlled environment where student strategies are run under standardised rules (slippage, bankruptcy checks, overspend guards, etc.).

\---

## Installation (Windows)

Follow these steps on a **fresh Windows machine**:

1. **Install Python**

&#x09;Download and install [Python 3.10+](https://www.python.org/downloads/).\\

&#x09;During installation, **tick "Add Python to PATH"**.

2\. **Unzip / Clone the Framework**

&#x09;Unzip the provided `BT396.zip`

&#x09;Place the folder somewhere convenient, e.g. `C:\\Users\\<YourName>\\BT396`.

4. **Open Command Prompt (cmd) or PowerShell**

&#x09;Navigate to the project root folder:


        cd C:\\Users\\<YourName>\\BT396
        

5. **Create a Virtual Environment (recommended)**

&#x20;   
    python -m venv venv
    venv\\Scripts\\activate
    

6. **Install Dependencies**

&#x20;   
    pip install --upgrade pip
    pip install backtrader pandas matplotlib pyyaml
    

   These are the core requirements:

   * `backtrader` – backtesting engine\\
   * `pandas` – data handling\\
   * `matplotlib` – plotting\\
   * `pyyaml` – config file support (optional, falls back to JSON)

\---

## Running the Backtester

The entry point is **`main.py`**.  
It takes a strategy (from the `strategies/` folder) and runs it against sample data in `DATA/`.

Basic usage:

``` bash
python main.py --strategy <name>
```

\---

## Example Runs

### 1\. Run the **Copycat** strategy

This is a simple demo strategy that goes long if yesterday’s close > open, otherwise short:

``` bash
python main.py --strategy copycat
```

### 2\. Run with **debug logging** enabled

This prints order fills, slippage, and trade PnL to the console:

``` bash
python main.py --strategy copycat --debug
```

### 3\. Run with a different dataset

If you have your own CSVs in a folder (must contain at least 10 aligned OHLCV files):

``` bash
python main.py --strategy copycat --data-dir ./DATA/MYCSV
```

### 4\. Run the **Portfolio Bankrupt Demo**

This shows what happens with extreme leverage and bad allocation:

``` bash
python main.py --strategy p\_bankrupt
```

\---

## 📂 Project Structure

```         
BT396/
│── main.py                 # Entry point
│── framework/              # Core framework (rules, analyzers, plotting)
│── strategies/             # Example + student strategies
│── DATA/                   # Sample CSV data
│── output/                 # Results are saved here
│── config.yaml             # Default config file
```

* Results (equity curves, JSON summaries, plots) are saved into the `output/` folder.
* You can override most settings via command line arguments (cash, commission, policies, etc.).

\---

## Next Steps

* Copy `strategies/template\_strategy.py` and start building your own trading ideas.\\
* Always test with:

&#x20;   ``` bash
    python main.py --strategy <your\_strategy>
    ```

* Check the `output/` folder for plots and summaries.

\---

Happy Backtesting…...

