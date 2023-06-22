from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
from smartworkers.pdf_smartworker import PdfSmartWorker

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/path/to/upload/directory'  # set this to your desired path
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/process_pdf', methods=['POST'])
def process_pdf():
    # Check if a file was posted
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']

    # If no file was selected, the user might have hit the submit button without choosing a file
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # If a file is present and it has an allowed extension, secure the filename and save it to the upload folder
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Initialize the SmartWorker
        contract = {}  # set the contract as per your requirement
        smart_worker = PdfSmartWorker(contract)
        response = smart_worker.process_pdf(filepath)

        return jsonify({"result": response})

    return jsonify({"error": "Unexpected error occurred"}), 500

if __name__ == '__main__':
    app.run(debug=True)
