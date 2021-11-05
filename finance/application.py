import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""

    if request.method == "POST":

        user_id = session["user_id"]

        rows = db.execute("SELECT * FROM portfolios WHERE user_id = :user_id",
                          user_id=user_id)

        # Check if user has any shares
        if len(rows) == 0:
            return apology("you don't own any shares")

        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=user_id)[0]["cash"]

        for row in rows:
            symbol = row["symbol"]
            shares = row["shares"]
            price = lookup(symbol)["price"]
            amount = shares * price

            # register transaction in the table "transactions"
            db.execute("INSERT INTO transactions (transac_type, symbol, shares, amount, user_id) VALUES (:transac_type, :symbol, :shares, :amount, :user_id)",
                        transac_type="sell", symbol=symbol, shares=shares, amount=amount, user_id=user_id)

            # remove the line from portfolio
            db.execute("DELETE FROM portfolios WHERE symbol = :symbol AND user_id = :user_id",
                        symbol=symbol, user_id=user_id)

            # update cash
            cash += amount
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id",
                        cash=cash, user_id=user_id)

        return redirect("/")

    else:
        user_id = session["user_id"]

        rows = db.execute("SELECT * FROM portfolios WHERE user_id = :user_id",
                              user_id=user_id)

        stock_total = 0

        for row in rows:
            symbol = row["symbol"]
            shares = row["shares"]
            price = lookup(symbol)["price"]
            value = shares * price
            row.update( {'price' : usd(price)} )
            row.update( {'value' : usd(value)} )
            stock_total += value

        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                              user_id=user_id)[0]["cash"]

        grand_total = stock_total + cash

        return render_template("index.html", rows=rows, cash=usd(cash), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide a symbol")

        if lookup(symbol) == None:
            return apology("symbol is incorrect")

        if not shares.isdigit():
            return apology("number of shares should be an integer")

        shares = int(shares)

        if not shares > 0:
            return apology("number of shares should be positive")

        price = lookup(symbol)["price"]
        amount = shares * price
        user_id = session["user_id"]

        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=user_id)[0]["cash"]

        if amount > cash:
            return apology("not enough money")

        else:
            # register transaction in the table "transactions" (user_id, timestamp, transac_type, symbol, shares, amount)
            db.execute("INSERT INTO transactions (transac_type, symbol, shares, amount, user_id) VALUES (:transac_type, :symbol, :shares, :amount, :user_id)",
                        transac_type="buy", symbol=symbol, shares=shares, amount=amount, user_id=user_id)

            # add number of shares to the user's portfolio in the table "portfolios" (user_id, symbol, shares)
            rows = db.execute("SELECT * FROM portfolios WHERE symbol = :symbol AND user_id = :user_id",
                          symbol=symbol, user_id=user_id)

            # if the user does not have shares of this stock, add a new line
            if len(rows) != 1:
                db.execute("INSERT INTO portfolios (symbol, shares, user_id) VALUES (:symbol, :shares, :user_id)",
                        symbol=symbol, shares=shares, user_id=user_id)

            # else, update value
            else:
                old_shares = db.execute("SELECT shares FROM portfolios WHERE symbol = :symbol AND user_id = :user_id",
                          symbol=symbol, user_id=user_id)[0]["shares"]
                db.execute("UPDATE portfolios SET shares = :new_shares WHERE symbol = :symbol AND user_id = :user_id",
                        new_shares=(old_shares+shares), symbol=symbol, user_id=user_id)

            # update cash
            cash -= amount
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id",
                        cash=cash, user_id=user_id)

        return redirect("/")


    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM transactions WHERE user_id = :user_id",
                          user_id=session["user_id"])

    for row in rows:
        row["amount"] = usd(row["amount"])
        row["transac_type"] = row["transac_type"].upper()

    return render_template("history.html", rows=rows)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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
            return apology("must provide symbol")

        if lookup(symbol) == None:
            return apology("symbol is incorrect")

        price = usd(lookup(symbol)["price"])
        return render_template('quoted.html', symbol=symbol.upper(), price=price)

    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        # Render an apology if the user’s input is blank
        if not username:
            return apology("must provide username", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)

        # Render an apology if username already exists
        if len(rows) != 0:
            return apology("username already taken", 403)

        # Render an apology if the user’s input is blank
        elif not password:
            return apology("must provide password", 403)

        # Render an apology if the passwords don't match
        elif password != request.form.get("confirmation"):
            return apology("passwords don't match", 403)

        # Submit the user’s input via POST to /register.

        hash = generate_password_hash(password)

        # INSERT the new user into users, storing a hash of the user’s password
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                    username=username, hash=hash)

        return redirect("/login ")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("must provide a symbol")

        if lookup(symbol) == None:
            return apology("symbol is incorrect")

        if not shares.isdigit():
            return apology("number of shares should be an integer")

        shares = int(shares)

        if not shares > 0:
            return apology("number of shares should be positive")

        price = lookup(symbol)["price"]
        amount = shares * price
        user_id = session["user_id"]

        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=user_id)[0]["cash"]

        shares_owned = db.execute("SELECT shares FROM portfolios WHERE user_id = :user_id AND symbol = :symbol",
                          user_id=user_id, symbol=symbol)[0]["shares"]

        # check if the user has enough shares
        if shares > shares_owned:
            return apology("not enough shares")

        else:

            # register transaction in the table "transactions"
            db.execute("INSERT INTO transactions (transac_type, symbol, shares, amount, user_id) VALUES (:transac_type, :symbol, :shares, :amount, :user_id)",
                        transac_type="sell", symbol=symbol, shares=shares, amount=amount, user_id=user_id)

            # remove the shares from the user's portfolio in the table "portfolios"
            old_shares = db.execute("SELECT shares FROM portfolios WHERE symbol = :symbol AND user_id = :user_id",
                          symbol=symbol, user_id=user_id)[0]["shares"]

            if old_shares == shares:
                # remove the line
                db.execute("DELETE FROM portfolios WHERE symbol = :symbol AND user_id = :user_id",
                            symbol=symbol, user_id=user_id)

            else:
                # update the number of shares
                db.execute("UPDATE portfolios SET shares = :new_shares WHERE symbol = :symbol AND user_id = :user_id",
                            new_shares=(old_shares-shares), symbol=symbol, user_id=user_id)

            # update cash
            cash += amount
            db.execute("UPDATE users SET cash = :cash WHERE id = :user_id",
                        cash=cash, user_id=user_id)

        return redirect("/")


    else:
        rows = db.execute("SELECT symbol FROM portfolios WHERE user_id = :user_id",
                            user_id=session["user_id"])
        return render_template("sell.html", rows=rows)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
