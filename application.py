from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash
from passlib.apps import custom_app_context as pwd_context

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure responses aren't cached
if app.config["DEBUG"]:
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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    #select each symbol owned by user and it's amount
    portfolio_symbols = db.execute("SELECT shares,symbol FROM portfolio WHERE user=:user", \
                        user=session["user_id"])

    #var to store total worth of portfolio
    total_worth = 0
    #loop through all the different stocks owned by user, and update
    #the values (current price,total value,)
    for portfolio_symbol in portfolio_symbols:
        shares= portfolio_symbol["shares"]
        symbol= portfolio_symbol["symbol"]
        stock = lookup(symbol)
        price = stock["price"]
        total = shares * stock["price"]
        total_worth += total
        #update the portfolio to show current value
        db.execute("UPDATE portfolio SET price=:price, total=:total WHERE user=:user AND symbol=:symbol", \
        price=usd(stock["price"]), total =usd(total), user=session["user_id"], symbol= symbol)
    #check to see what the user has in cash, add to the total worth var.
    cash_now = db.execute("SELECT cash FROM users WHERE id=:id",\
                id=session["user_id"])
    total_worth+=cash_now[0]["cash"]
    #Select all the info in the updated portfolio to be used for html form.
    updated_port = db.execute("SELECT * FROM portfolio WHERE user=:user",user=session["user_id"])

    return render_template("index.html", stocks=updated_port,cash=usd(cash_now[0]["cash"]),\
                            total= usd(total_worth) )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        #Ensure proper inputs
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Please enter a valid stock symbol")

        try:
            shares = int(request.form.get("shares"))
            if shares <= 0:
                return apology("please enter a positive integer")
        except:
            return apology("please enter a positive integer for shares")

        #Get users available cash and ensure they have enough to purchase stock
        money = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])

        if not money or float(money[0]["cash"]) < stock["price"] * shares:
            return apology("Not enough money")


        #insert into users history
        db.execute("INSERT INTO history (user, stock, price, shares) VALUES(:user, :stock, :price, :shares)", user= session["user_id"], \
                    stock = stock["symbol"], price=usd(stock["price"]),  shares =shares)
        # update the users cash
        db.execute("UPDATE users SET cash = cash - :purchase WHERE id = :id", \
                    id =session["user_id"] , purchase = stock["price"] * float(shares))
        # select users shares of that stock
        owned_shares = db.execute("SELECT shares FROM portfolio WHERE user=:id AND symbol=:symbol",\
                        id=session["user_id"], symbol=stock["symbol"])

        # if the user does not own any shares of the stock, create a new column
        if not owned_shares:
            db.execute("INSERT INTO portfolio (user, name, shares, price, symbol) VALUES(:user, :name, :shares, :price, :symbol)", \
                        user = session["user_id"], name = stock["name"], shares = shares, price = stock["price"], symbol = stock["symbol"])
        else:
            new_shares = owned_shares[0]["shares"] + shares
            db.execute("UPDATE portfolio SET shares = :shares WHERE user=:user AND symbol= :symbol", \
                        shares = new_shares, user =session["user_id"], symbol = stock["symbol"])
        #return user to index
        return redirect(url_for("index"))
    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    #select all from the history table for the user
    histories= db.execute("SELECT * FROM history WHERE user=:user", \
                        user=session["user_id"])

    return render_template("history.html", histories=histories)


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
    """Get Stock quote."""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("Enter a symbol.")

        rows = lookup(request.form.get("symbol"))

        if not rows:
            return apology("stock does not exist")

        return render_template("quoted.html", stock=rows)

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    #forget any user_id
    session.clear()
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        #ensure  username is not blank
        if not request.form.get("username"):
            return apology("missing username")

        #ensure password is not blank
        elif not request.form.get("password"):
            return apology("missing password")

        #ensure password and password confirmation match
        elif request.form.get("password") != request.form.get("pword"):
            return apology("passwords don't match!")

        # insert the new user into users, storing the hash of the user's password
        result = db.execute("INSERT INTO users (username, hash) \
                             VALUES(:username, :hash)", \
                             username=request.form.get("username"), \
                             hash=generate_password_hash(request.form.get("password")))

        if not result:
            return apology("Username already exist")

        #log the user in
        session["user_id"] = result
        #direct ro home page
        return redirect("/")

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        #ensure iputs are valid
        if not request.form.get("symbol"):
            return apology("missing symbol")

        elif not request.form.get("shares"):
            return apology("missing shares")

        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Please enter a valid stock symbol")
        shares = int(request.form.get("shares"))

        #insert into users history
        db.execute("INSERT INTO history (user, stock, price, shares) VALUES(:user, :stock, :price, :shares)", user= session["user_id"], \
                    stock = stock["symbol"], price=usd(stock["price"]),  shares =(-shares))
        # select users shares of that stock
        owned_shares = db.execute("SELECT shares FROM portfolio WHERE user=:id AND symbol=:symbol",\
                        id=session["user_id"], symbol=stock["symbol"])
        # if the user does not own any shares of the stock,or not enough, return apology
        if not owned_shares or int(owned_shares[0]["shares"]) < shares:
            return apology("Not enough shares")
        #update users portfolio
        new_shares = owned_shares[0]["shares"] - shares
        db.execute("UPDATE portfolio SET shares = :shares WHERE user=:user AND symbol= :symbol", \
                        shares = new_shares, user =session["user_id"], symbol = stock["symbol"])
        #update users cash
        # update the users cash
        db.execute("UPDATE users SET cash = cash + :sale WHERE id = :id", \
                    id =session["user_id"] , sale = stock["price"] * float(shares))


        return redirect("/")

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")

@app.route("/refill", methods=["GET", "POST"])
@login_required
def refill():
    if request.method == "POST":
        new_cash=int(request.form.get("cash"))
        db.execute("UPDATE users SET cash = cash + :new_cash WHERE id = :id", \
                    id =session["user_id"] , new_cash = new_cash)
        return redirect("/")
    else:
        return render_template("refill.html")

def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
