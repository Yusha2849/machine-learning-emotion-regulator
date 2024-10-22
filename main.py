# Non-personal imports
from flask import Flask, json, jsonify,  render_template, abort, redirect, url_for, request, flash
from datetime import date
from flask_wtf.csrf import CSRFProtect
from markupsafe import escape
from flask_mail import Mail, Message
import os

# Personal imports
from units.db_populate import populate_emotioncolour,check_database_existence
from units.forms import UserEmotionDescription, ContactForm
from units.DAO import EmotionColourDAO,RecordDAO
from units.db_init import init_db
from units.NLP import NLP

# Result imports
from flask_socketio import SocketIO
import matplotlib.pyplot as plt
from io import BytesIO
import base64

app = Flask(__name__)

socketio = SocketIO(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///project.db"

app.config['SECRET_KEY'] = 'your_secret_key_here'

# Configure Flask-Mail
app.config["MAIL_SERVER"] = 'smtp.gmail.com'
app.config["MAIL_PORT"] = 465
app.config['MAIL_USERNAME'] = os.environ.get('ATTENDANCE_EMAIL')
app.config['MAIL_PASSWORD'] = os.environ.get('ATTENDANCE_EMAIL_PASS')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('ATTENDANCE_EMAIL')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True    
mail = Mail(app) 

# Enable CSRF protection
csrf = CSRFProtect(app)

NLP.setup()

COLOUR_COLUMNS = [
    ['black', "#000000"],
    ['red', "#FF0000"],
    ['gray', "#808080"],
    ['yellow', "#FFFF00"],
    ['light_purple', "#D8BFD8"],
    ['sky_blue', "#87CEEB"],
    ['jade', "#00A86B"],
    ['green', "#008000"],
    ['aqua', "#00FFFF"],
    ['indigo', "#4B0082"],
    ['blue', "#0000FF"],
    ['bright_pink', "#FF007F"],
    ['chocolate', "#D2691E"],
    ['dark_yellow', "#FFD700"],
    ['light_green', "#90EE90"]
]

# General routes ---------------------------------------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.errorhandler(404)
def page_not_found(error):
    return render_template('page_not_found.html'), 404
# Emotion Regulator main functionality related routes --------------------------------------------------------------------

@app.route("/emotion_description",methods=["GET","POST"])
def emotion_description():
    form = UserEmotionDescription()
    if form.validate_on_submit():
        description = form.description.data
        return redirect(url_for("display_colour",emotion_name=description))
    return render_template("emotion_description.html",form=form)

@app.route("/display_colour/<emotion_name>")
def display_colour(emotion_name):
    
    emotion_name = NLP.operate(escape(emotion_name)).capitalize()
    print(emotion_name)
    emotions = [emotion.emotion_name for emotion in EmotionColourDAO.get_all_emotions()]
    
    if emotion_name not in emotions:
        abort(404)
    
    result = EmotionColourDAO.get_emotion_colours(emotion_name,
                                                  available_colours=[c[0] for c in COLOUR_COLUMNS])
    if not result:
        abort(500)
    
    organised_colours = organise_colours(add_colour_hex_pairs(result))
    print(organised_colours)
    # return render_template("display_colour.html")
    return render_template("display_colour.html",colour_list=organised_colours,emotion_name=emotion_name)


@app.route('/process_results', methods=['POST'])
def process_results():
    print("reached")
    data = request.get_json()  # Safely get JSON data from the POST request
    if not data or 'results' not in data:
        return jsonify({'message': 'Bad request, results not found'}), 400

    results = data.get('results')  # Extract the list of results (0s and 1s)
    colours = data.get('colours')
    emotion_name = data.get('emotion_name')
    # Debugging: Print the results received on the server
    # print("Received results:", results)
    # print("Colours:",colours)
    # print("Emotion name:",emotion_name)
    
    shortened_colour_list = calculate_updated_colour_list(results,colours)
    paired_colour_rating_list = pair_colour_and_rating(results,shortened_colour_list)
    manage_record(paired_colour_rating_list,emotion_name)
    # Respond with a success message
    return jsonify({'message': 'Results processed successfully!'}), 200


# Helper functions ---------------------------------------------------------------------------------------------------


def manage_record(n_list, emotion_name):
    # Fetch the emotion record using the DAO
    record = EmotionColourDAO.get_emotion_record_by_emotion(emotion_name)

    if not record:
        print(f"No record found for emotion: {emotion_name}")
        return

    # Fetch the current sample size
    sample_size = record.sample_size

    # Loop through the n_list and update each column
    updates = {}
    for n in n_list:
        colour = n[0]
        choice = n[1]

        # Dynamically get the current value of the colour
        value = getattr(record, colour, None)
        if value is None:
            print(f"Invalid column: {colour}")
            continue

        # Calculate the new value
        new_value = calculate_updated_value(value, choice, sample_size)
        
        colour_match = False
        if choice == 1:
            colour_match = True
        
        RecordDAO.create_record(
            emotion_name=emotion_name,
            likelihood_score=value,
            colour_displayed=colour,
            record_date=date.today(),
            colour_match=colour_match
        )
        # Store the updated value in a dictionary for batch updating
        updates[colour] = new_value

    # Increment the sample size
    updates["sample_size"] = sample_size + 1

    # Use the DAO to apply the updates to the database
    EmotionColourDAO.update_emotion(record.emotion_id, **updates)
    print(f"Successfully updated record for {emotion_name}")


def calculate_updated_value(value,choice,sample_size):
    new_value = 0
    contribution = calculate_contribution(value,sample_size)
    if choice == 0:
        new_value = decrement_value(value,contribution)
        if value < 0:
            new_value = 0
    elif choice == 1:
        new_value = increment_value(value,contribution)
        if value > 10:
            new_value = 10
    
    return new_value
        

def calculate_contribution(current_value,sample_size):
    return current_value/sample_size

def increment_value(current_value,contribution):
    return current_value + contribution
    
def decrement_value(current_value,contribution):
    return current_value - contribution
    

def pair_colour_and_rating(results,colour_list):
    colour_rating_list = []
    for i in range(len(results)):
        c = colour_list[i][0]
        r = results[i]
        colour_rating_list.append([c,r])
    return colour_rating_list

def calculate_updated_colour_list(results,colours):
    new_list = colours[:len(results)]
    return new_list


def add_colour_hex_pairs(colour_dict):
    colour_list_to_dict = {colour[0]: colour[1] for colour in COLOUR_COLUMNS}
    temp_dict = {}
    for key in colour_dict:
        temp_dict[key] = [colour_dict[key],colour_list_to_dict[key]]
    
    return temp_dict
        
        
def organise_colours(colour_dict):
    sorted_list = sorted(colour_dict.items(),key=lambda x:x[1],reverse=True)
    
    return sorted_list

# Record related routes --------------------------------------------------------------------------------------------------

@app.route("/records", methods=["GET"])
def get_records():
    records = RecordDAO.get_all_records()
    if not records:
        return "No records available"
    return jsonify([{
        "record_id": record.record_id,
        "emotion_name": record.emotion_name,
        "likelihood_score": record.likelihood_score,
        "colour_displayed": record.colour_displayed,
        "record_date": record.record_date,
        "colour_match": record.colour_match
    } for record in records])

@app.route("/records/<int:record_id>", methods=["GET"])
def get_record_by_id(record_id):
    record = RecordDAO.find_record_by_id(record_id)
    if record:
        return jsonify({
            "record_id": record.record_id,
            "emotion_name": record.emotion_name,
            "likelihood_score": record.likelihood_score,
            "colour_displayed": record.colour_displayed,
            "record_date": record.record_date,
            "colour_match": record.colour_match
        })
    return jsonify({"error": "Record not found"}), 404

@app.route("/records", methods=["POST"])
def create_record():
    data = request.json
    new_record = RecordDAO.add_record(
        emotion_name=data.get("emotion_name"),
        likelihood_score=data.get("likelihood_score"),
        colour_displayed=data.get("colour_displayed"),
        record_date=date.fromisoformat(data.get("record_date")),
        colour_match=data.get("colour_match")
    )
    return jsonify({
        "record_id": new_record.record_id,
        "emotion_name": new_record.emotion_name,
        "likelihood_score": new_record.likelihood_score,
        "colour_displayed": new_record.colour_displayed,
        "record_date": new_record.record_date,
        "colour_match": new_record.colour_match
    }), 201

@app.route("/records/<int:record_id>", methods=["PUT"])
def update_record(record_id):
    data = request.json
    updated_record = RecordDAO.update_record(
        record_id,
        emotion_name=data.get("emotion_name"),
        likelihood_score=data.get("likelihood_score"),
        colour_displayed=data.get("colour_displayed"),
        record_date=date.fromisoformat(data.get("record_date")),
        colour_match=data.get("colour_match")
    )
    if updated_record:
        return jsonify({
            "record_id": updated_record.record_id,
            "emotion_name": updated_record.emotion_name,
            "likelihood_score": updated_record.likelihood_score,
            "colour_displayed": updated_record.colour_displayed,
            "record_date": updated_record.record_date,
            "colour_match": updated_record.colour_match
        })
    return jsonify({"error": "Record not found"}), 404

@app.route("/records/<int:record_id>", methods=["DELETE"])
def delete_record(record_id):
    if RecordDAO.delete_record(record_id):
        return jsonify({"message": "Record deleted successfully"})
    return jsonify({"error": "Record not found"}), 404

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if request.method == 'POST':
        # Validate the form using the `validate_on_submit` method
        if form.validate_on_submit():
            name = form.name.data
            email = form.email.data
            message = form.message.data

            # Send email
            msg = Message(subject=f'New Contact Form Submission from {name}',
                          sender=os.environ.get('ATTENDANCE_EMAIL'),
                          recipients=[email, 'digitalattendance05@gmail.com'],  # Replace with your recipient email
                          body=f'Name: {name}\nEmail: {email}\nMessage: {message}')
            mail.send(msg)
            
            # Handle form submission (e.g., send email or store in database)
            flash("Thank you for contacting us!", "success")
            return redirect('/contact')  # Redirect to prevent form re-submission
        else:
            flash("Please fill out all fields correctly.", "error")

    return render_template('contact.html', form=form)  # Pass the form to the template

# Define emotions with their color values
emotions = {
    "Anger": {"black": 4.5, "red": 8.6, "gray": 1.0, "yellow": 0, "light_purple": 0, "sky_blue": 0, "jade": 0, "green": 0, "aqua": 0, "indigo": 0.5, "blue": 0, "bright_pink": 0, "chocolate": 0, "dark_yellow": 0, "light_green": 0},
    "Calmness": {"black": 0, "red": 0, "gray": 0, "yellow": 0, "light_purple": 2.3, "sky_blue": 3.1, "jade": 0, "green": 0, "aqua": 1.6, "indigo": 0, "blue": 2.4, "bright_pink": 0, "chocolate": 0, "dark_yellow": 0, "light_green": 0},
    "Contempt": {"black": 1.7, "red": 0, "gray": 1.0, "yellow": 0, "light_purple": 1.2, "sky_blue": 0, "jade": 0, "green": 0.5, "aqua": 0, "indigo": 0, "blue": 0.5, "bright_pink": 0.6, "chocolate": 0.7, "dark_yellow": 0.8, "light_green": 0},
    "Disgust": {"black": 0, "red": 0, "gray": 0, "yellow": 0, "light_purple": 0, "sky_blue": 0, "jade": 0.5, "green": 0.5, "aqua": 0, "indigo": 0, "blue": 0, "bright_pink": 0, "chocolate": 3.6, "dark_yellow": 3.2, "light_green": 3.1},
    "Envy": {"black": 0, "red": 1.7, "gray": 0, "yellow": 0, "light_purple": 0, "sky_blue": 0, "jade": 2.7, "green": 3.0, "aqua": 0, "indigo": 0, "blue": 0, "bright_pink": 0, "chocolate": 0, "dark_yellow": 0, "light_green": 1.4},
    "Fear": {"black": 5.7, "red": 2.5, "gray": 1.6, "yellow": 1.0, "light_purple": 0, "sky_blue": 0, "jade": 0, "green": 0, "aqua": 0, "indigo": 0.9, "blue": 0, "bright_pink": 0, "chocolate": 0, "dark_yellow": 0, "light_green": 0},
    "Happiness": {"black": 0, "red": 0, "gray": 0, "yellow": 5.3, "light_purple": 0, "sky_blue": 2.6, "jade": 0, "green": 0, "aqua": 2.3, "indigo": 0, "blue": 0.6, "bright_pink": 1.4, "chocolate": 0, "dark_yellow": 0, "light_green": 0},
    "Jealousy": {"black": 0, "red": 2.6, "gray": 0, "yellow": 0, "light_purple": 0, "sky_blue": 0, "jade": 2.4, "green": 2.3, "aqua": 0, "indigo": 0, "blue": 0, "bright_pink": 0, "chocolate": 0, "dark_yellow": 0, "light_green": 1.4},
    "Sadness": {"black": 2.4, "red": 0, "gray": 4.2, "yellow": 0, "light_purple": 0, "sky_blue": 0, "jade": 0, "green": 0, "aqua": 0, "indigo": 3.4, "blue": 0, "bright_pink": 0, "chocolate": 0.8, "dark_yellow": 0, "light_green": 0},
    "Surprise": {"black": 0, "red": 0, "gray": 0, "yellow": 2.6, "light_purple": 0.9, "sky_blue": 0.6, "jade": 0, "green": 0, "aqua": 2.1, "indigo": 0, "blue": 0, "bright_pink": 2.6, "chocolate": 0, "dark_yellow": 0, "light_green": 0}
}

available_colours = ["black", "red", "gray", "yellow", "light_purple", "sky_blue", "jade", "green", "aqua", "indigo", "blue", "bright_pink", "chocolate", "dark_yellow", "light_green"]

# Function to plot the emotion bar charts and return the image in base64 format
def plot_emotion_bars(emotion_name, dataset_color_values, system_color_values):
    fig, axs = plt.subplots(1, 2, figsize=(10, 5))

    # Dataset graph (left)
    dataset_colors = list(dataset_color_values.keys())
    dataset_values = list(dataset_color_values.values())
    axs[0].bar(dataset_colors, dataset_values, color='lightblue')
    axs[0].set_title(f'Dataset - {emotion_name}')
    axs[0].set_xlabel('Colours')
    axs[0].set_ylabel('Impact Value')
    axs[0].set_xticklabels(dataset_colors, rotation=45, ha="right")

    # System graph (right)
    system_colors = list(system_color_values.keys())
    system_values = list(system_color_values.values())
    axs[1].bar(system_colors, system_values, color='lightgreen')
    axs[1].set_title(f'System - {emotion_name}')
    axs[1].set_xlabel('Colours')
    axs[1].set_ylabel('Impact Value')
    axs[1].set_xticklabels(system_colors, rotation=45, ha="right")

    plt.tight_layout()

    # Convert plot to base64 image
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close(fig)

    return image_base64

@app.route('/results')
def results():
    emotion_graphs = []
    for emotion, dataset_color_values in emotions.items():
        # Get the latest system data for the current emotion
        system_color_values = EmotionColourDAO.get_emotion_colours(emotion, available_colours)

        if system_color_values:
            # Plot the graphs for both dataset and system
            emotion_graph = plot_emotion_bars(emotion, dataset_color_values, system_color_values)
            emotion_graphs.append((emotion, emotion_graph))

    return render_template('result.html', emotion_graphs=emotion_graphs)

# Running the app -------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():

        if not check_database_existence(filepath="instance/project.db"):
            init_db(app=app)
            populate_emotioncolour()
        else:
            init_db(app=app)
        
        # Run the Flask app
        socketio.run(app, debug=True)
        #app.run(debug=True)
