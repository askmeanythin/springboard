@app.route("/register")
def register_page():
    return render_template("register.html")