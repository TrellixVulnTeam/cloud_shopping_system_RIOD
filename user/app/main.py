from flask import render_template, session, redirect, request, url_for, flash
import hashlib
from app import app
from app import dynamo
from app import s3_config

# set secret key for session
app.secret_key = '\x86j\x94\xab\x15\xedy\xe4\x1f\x0b\xe9\xb9v}C\xb9\xf1\xech\x0bs.\x10$'
ALLOWED_EXTENSIONS = set(['jpg', 'png', 'gif'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def getLoginDetails():
    if ('email' not in session) or not dynamo.check_table_availability('users') or \
            not dynamo.check_table_availability('categories') or not dynamo.check_table_availability('products') \
            or not dynamo.check_table_availability('kart'):
        loggedIn = False
        firstName = ''
        noOfItems = 0
        userId = 0
    else:
        loggedIn = True
        record=dynamo.users_email_userId(session['email'])
        if len(record) != 0:
            userId = record[0][1]
            record=dynamo.users_email_firstName(session['email'])
            firstName = record[0][1]
            record=dynamo.kart_userId_productId(userId)
            noOfItems = 0
            i = 0
            while i < len(record):
                noOfItems = noOfItems + record[i]['amount']
                i = i + 1
        else:
            session.pop("email", None)
            loggedIn = False
            firstName = ''
            noOfItems = 0
            userId = 0
    return (loggedIn, firstName,noOfItems,userId)

@app.route("/")
def root():
    loggedIn, firstName, noOfItems,userId = getLoginDetails()
    itemData=dynamo.products_list_all()
    categoryData=dynamo.categories_list_all()

    return render_template('home.html', itemData=itemData,loggedIn=loggedIn,firstName=firstName, noOfItems=noOfItems, categoryData=categoryData)

@app.route("/search", methods = ["POST"])
def search():
    if request.method == "POST":
        loggedIn, firstName, noOfItems, userId = getLoginDetails()
        itemData = dynamo.products_list_all()
        categoryData = dynamo.categories_list_all()
        searchkeyword = request.form['search']
        result = []
        for item in itemData:
            for row in item:
                if searchkeyword in row[1]:
                    result.append([row])
        return render_template('home.html', itemData=result, loggedIn=loggedIn, firstName=firstName, noOfItems=noOfItems,
                               categoryData=categoryData)

@app.route("/submit_order",methods = ["POST"])
def submit_order():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    kart = dynamo.kart_get(userId)
    totalPrice = 0
    if len(kart) != 0:
        msg = ""
        i = 0
        order_description = ""
        while i < len(kart):
            stock_status = dynamo.stock_update(kart[i][1], kart[i][2])
            if stock_status[0] == 0:
                order_description = order_description + str(kart[i][3]) + " × " + str(kart[i][2]) + " | "
                totalPrice = totalPrice + float(kart[i][6])
            elif stock_status[0] == -1:
                msg = stock_status[1]
                for item in kart:
                    dynamo.kart_removeAll(userId, int(item[1]))
                kart = dynamo.kart_get(userId)
                loggedIn, firstName, noOfItems, userId = getLoginDetails()
                totalPrice = 0
                return render_template("cart.html", msg=msg,
                                       products=kart, totalPrice=totalPrice, loggedIn=loggedIn, firstName=firstName,
                                       noOfItems=noOfItems)
            else:
                order_description = order_description + str(kart[i][3]) + " × " + str(stock_status[0]) + " | "
                msg = msg + stock_status[1]
                totalPrice = totalPrice + float(int(stock_status[0]) * float(kart[i][5]) )

            i = i + 1
        dynamo.order_put(userId, order_description, str(format(totalPrice,'.2f')), "processing")
        for item in kart:
            dynamo.kart_removeAll(userId,int(item[1]))

        kart = dynamo.kart_get(userId)
        loggedIn, firstName, noOfItems, userId = getLoginDetails()
        totalPrice = 0
        msg = msg + "Your order has been submitted, Thanks for shopping!"
    else:
        msg = "Your cart is empty !"
    return render_template("cart.html",msg = msg,
                           products = kart, totalPrice=totalPrice, loggedIn=loggedIn, firstName=firstName, noOfItems=noOfItems)


@app.route("/account/orders")
def viewOrders():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    orders = dynamo.orders_get(userId)
    if len(orders) == 0:
        msg = "No order record"
        return render_template("orders.html",msg = msg, loggedIn=loggedIn, firstName=firstName, noOfItems=noOfItems)
    else:
        return render_template("orders.html", orders=orders, loggedIn=loggedIn, firstName=firstName,
                               noOfItems=noOfItems)




@app.route("/displayCategory")
def displayCategory():
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    categoryId = request.args.get("categoryId")
    categoryName = dynamo.get_category_name(int(categoryId))
    data = dynamo.products_in_category(int(categoryId))
    return render_template('displayCategory.html',data=data, loggedIn=loggedIn, firstName=firstName, noOfItems=noOfItems, categoryName=categoryName[0])


@app.route("/account/profile")
def profileHome():
    if 'email' not in session:
        return redirect(url_for('root'))
    loggedIn,firstName,noOfItems, userId=getLoginDetails()
    return render_template('profileHome.html', loggedIn=loggedIn,firstName=firstName,noOfItems=noOfItems)

@app.route("/account/profile/view")
def viewProfile():
    if 'email' not in session:
        return redirect(url_for('root'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    profileData=dynamo.users_email_all(session['email'])
    return render_template('viewProfile.html',profileData=profileData,loggedIn=loggedIn,firstName=firstName,noOfItems=noOfItems)


@app.route("/account/profile/edit")
def editProfile():
    if 'email' not in session:
        return redirect(url_for('root'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    profileData=dynamo.users_email_all(session['email'])
    return render_template('editProfile.html',profileData=profileData,loggedIn=loggedIn,firstName=firstName,noOfItems=noOfItems)


@app.route("/account/profile/changePassword", methods=["GET", "POST"])
def changePassword():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    if request.method == "POST":
        oldPassword = request.form['oldpassword']
        oldPassword = hashlib.md5(oldPassword.encode()).hexdigest()
        newPassword = request.form['newpassword']
        newPassword = hashlib.md5(newPassword.encode()).hexdigest()
        data=dynamo.users_email_password(session['email'])
        password = data[0][1]
        data=dynamo.users_email_userId(session['email'])
        userId = data[0][1]
        if (password == oldPassword):
            dynamo.users_update_password_userId(userId,newPassword)
            msg="Changed successfully"
            return render_template("changePassword.html", msg=msg)
        else:
            msg = "Old password does not match system record"
            return render_template("changePassword.html", msg=msg)
    else:
        return render_template("changePassword.html")


@app.route("/updateProfile", methods=["POST"])
def updateProfile():
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    if loggedIn:
        if request.method == 'POST':
            firstName = request.form['firstName']
            lastName = request.form['lastName']
            address1 = request.form['address1']
            address2 = request.form['address2']
            zipcode = request.form['zipcode']
            city = request.form['city']
            province = request.form['province']
            country = request.form['country']
            phone = request.form['phone']

            if (firstName == ''):
                msg = "firstname cannot be empty"
                profileData = dynamo.users_email_all(session['email'])
                return render_template("editProfile.html", error=msg,profileData=profileData,loggedIn=loggedIn,firstName=firstName,noOfItems=noOfItems)
            else:
                userdetail = [lastName, address1, address2, zipcode, city, province, country, phone]

                i = 0
                while i < len(userdetail):
                    if userdetail[i] == '':
                        userdetail[i] = " "
                    i = i + 1
                dynamo.users_update_all_userId(userId, session['email'], firstName, userdetail)
                profileData = dynamo.users_email_all(session['email'])
                msg = "Updated Successfully"
                return render_template("editProfile.html", error=msg,profileData=profileData,loggedIn=loggedIn,firstName=firstName,noOfItems=noOfItems)
    else:
        return redirect(url_for('root'))


@app.route("/loginForm")
def loginForm():
    if 'email' in session:
        return redirect(url_for('root'))
    else:
        return render_template('login.html',error='')


@app.route("/login", methods=["POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']
        if is_valid(email,password):
            session['email'] = email
            return redirect(url_for('root'))
        else:
            msg = "Invalid email or password"
            return render_template('login.html', error = msg)


@app.route("/productDescription")
def productDescription():
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    productId = request.args.get('productId')
    productData=dynamo.products_productId_search(int(productId))
    imageurl = s3_config.get_element_from_bucket('ece1779_a3_bucket', productData[0]['image'])
    productData[0]['image'] = imageurl
    return render_template("productDescription.html",data=productData,loggedIn=loggedIn,firstName=firstName,noOfItems=noOfItems)


@app.route("/addToCart")
def addToCart():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    else:
        record = dynamo.users_email_userId(session['email'])
        userId = record[0][1]
        productId = int(request.args.get('productId'))
        dynamo.kart_put(userId,int(productId),1)
        return redirect(url_for('root'))


@app.route("/cart")
def cart():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    kart = dynamo.kart_get(userId)
    totalPrice = 0
    i = 0
    while i < len(kart):
        totalPrice = totalPrice + float(kart[i][6])
        i = i + 1
    return render_template("cart.html",products = kart, totalPrice=format(totalPrice,'.2f'), loggedIn=loggedIn, firstName=firstName, noOfItems=noOfItems)


@app.route("/removeOneFromCart")
def removeOneFromCart():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    productId = int(request.args.get('productId'))
    dynamo.kart_removeOne(userId, productId)
    return redirect(url_for('cart'))

@app.route("/removeAllFromCart")
def removeAllFromCart():
    if 'email' not in session:
        return redirect(url_for('loginForm'))
    loggedIn, firstName, noOfItems, userId = getLoginDetails()
    productId = int(request.args.get('productId'))
    dynamo.kart_removeAll(userId, productId)
    return redirect(url_for('cart'))

@app.route("/logout")
def logout():
    session.pop("email", None)
    return redirect(url_for("root"))


def is_valid(email, password):
    data = dynamo.users_email_password(email)
    if len(data) != 0:
        if data[0][0] == email and data[0][1] == hashlib.md5(password.encode()).hexdigest():
            return True
        return False
    return False


@app.route("/register", methods=["POST"])
def register():
    if request.method == "POST":
        password = request.form['password']
        email = request.form['email']
        firstName = request.form['firstName']
        lastName = request.form['lastName']
        address1 = request.form['address1']
        address2 = request.form['address2']
        zipcode = request.form['zipcode']
        city = request.form['city']
        province = request.form['province']
        country = request.form['country']
        phone = request.form['phone']

        if (password == '' or email == '' or firstName == ''):
            msg = "email, password , firstname cannot be empty"
            return render_template("register.html", error=msg)
        else:

            userdetail = [lastName,address1,address2,zipcode,city,province,country,phone]
            i = 0
            while i < len(userdetail):
                if userdetail[i] == '':
                    userdetail[i] = " "
                i = i + 1
            check_email = dynamo.users_email_userId(email)
            if len(check_email) == 0:
                dynamo.users_put(hashlib.md5(password.encode()).hexdigest(), email, firstName, userdetail)
                msg = "Registered Successfully"
            else:
                msg = "Email already exists, please register with another one"
            return render_template("login.html", error=msg)


@app.route("/registrationForm")
def registrationForm():
    return render_template("register.html")
