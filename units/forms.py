from flask_wtf import FlaskForm
from wtforms import StringField,SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email

class UserEmotionDescription(FlaskForm):
    description = StringField("Describe the emotion you want to feel",validators=[DataRequired()])
    submitfield = SubmitField(label="CONFIRM")

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('SEND MESSAGE')