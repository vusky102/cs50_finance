import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio=[]
    asset_total=0
    username= db.execute("select username from users where id=?", session["user_id"])[0]["username"]

    rows=db.execute("select symbol,sum(shares) from history where username=? group by symbol having sum(shares)>0",username)
    for row in rows:
        price = lookup(row["symbol"])["price"]
        total = price * row["sum(shares)"]
        portfolio.append({
        "symbol": row["symbol"].upper(),
        "shares": row["sum(shares)"],
        "price": f"{price:,.2f}",
        "total": f"{total:,.2f}"
        })
        asset_total+= float(total)

    cash_data = db.execute("select cash from users where username=?",username)
    cash_num=cash_data[0]['cash']
    final_total = cash_num+ asset_total

    cash = f"{cash_data[0]['cash']:,.2f}"
    return render_template("index.html",cash=cash,final_total=f"{final_total:,.2f}",portfolio=portfolio)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Validate symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must provide symbol")

        # Validate shares
        try:
            shares = request.form.get("shares")
            if not shares:
                return apology("Must provide number of shares")

            shares = int(shares)
            if shares <= 0:
                return apology("Number of shares must be positive")

        except ValueError:
            return apology("Shares must be a whole number")

        # Lookup stock
        response = lookup(symbol)
        if response is None:
            return apology("Invalid symbol")

        price = float(response["price"])
        username = db.execute("select username from users where id=?", session["user_id"])[0]["username"]
        balance = db.execute("select cash from users where id=?", session["user_id"])[0]["cash"]
        require_balance = price * shares

        if require_balance > balance:
            return apology("Insufficient balance")

        # Execute transaction
        db.execute("insert into history (username,symbol,shares,price) values (?,?,?,?)",
                  username, symbol.upper(), shares, price)
        db.execute("update users set cash = cash - ? where username=?",
                  require_balance, username)

        flash(f"Bought {shares} shares of {symbol.upper()} for ${require_balance:,.2f}")
        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    username=db.execute("select username from users where id=?", session["user_id"])[0]["username"]
    history=db.execute("select * from history where username=?",username)
    if len(history)==0:
        return render_template("no_history.html")
    return render_template("history.html",history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must provide symbol")

        response = lookup(symbol)
        if response is None:
            return apology("Invalid symbol")

        # Format the price to exactly 2 decimal places
        response["price"] = float(response["price"])
        return render_template("quoted.html", response=response)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method=="POST":
        username= request.form.get("username").lower()
        password= request.form.get("password")
        hashedpassword= generate_password_hash(password)
        confirmation= request.form.get("confirmation")
        check_username= db.execute("select * from users where username=?",username)

        if not username:
            error="Username is required."
        elif not password:
            error="Password is required."
        elif password != confirmation:
            error="Password do not match."
        elif len(check_username) !=0:
            error="Username exists."
        else:
            session.clear()

            db.execute("insert into users(username,hash) values (?,?)",username,hashedpassword)

            check_username= db.execute("select * from users where username=?",username)

            flash("Registered!")
            cash = db.execute("select cash from users where username=?",username)
            cash = f"{cash[0]['cash']:,.2f}"
            session["user_id"] = check_username[0]["id"]

            return render_template("index.html",cash=cash)
        return apology(error)

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    symbol_list = []
    username = db.execute("select username from users where id=?", session["user_id"])[0]["username"]
    rows = db.execute("""
        select symbol, sum(shares) as total_shares
        from history
        where username = ?
        group by symbol
        having sum(shares) > 0
    """, username)

    for row in rows:
        symbol_list.append(row["symbol"].upper())

    if request.method == "POST":
        # Validate symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must select a symbol")

        # Validate shares
        try:
            shares = request.form.get("shares")
            if not shares:
                return apology("Must provide number of shares")

            shares = int(shares)
            if shares <= 0:
                return apology("Number of shares must be positive")

        except ValueError:
            return apology("Shares must be a whole number")

        # Look up stock price
        response = lookup(symbol)
        if response is None:
            return apology("Invalid symbol")

        price = float(response["price"])

        # Get current shares balance
        shares_data = db.execute("""
            select sum(shares) as total_shares
            from history
            where symbol = ? and username = ?
        """, symbol.upper(), username)[0]["total_shares"]

        if shares_data is None:
            return apology("You don't own any shares of this stock")

        if shares > shares_data:
            return apology(f"You only have {shares_data} shares available to sell")

        # Calculate sell amount and update database
        sell_amount = price * shares

        db.execute("""
            insert into history (username, symbol, shares, price)
            values (?, ?, ?, ?)
        """, username, symbol.upper(), -shares, price)

        db.execute("""
            update users
            set cash = cash + ?
            where username = ?
        """, sell_amount, username)

        flash(f"Sold {shares} shares of {symbol.upper()} for ${sell_amount:,.2f}")
        return redirect("/")

    return render_template("sell.html", symbol_list=symbol_list)
