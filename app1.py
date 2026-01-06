
from flask import Flask, send_from_directory, request
import os

app = Flask(__name__)

# 设定静态文件目录
app.config['UPLOAD_FOLDER'] = 'uploads'
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
def index():
    return "欢迎来到文件服务器!"

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            filename = file.filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return '文件上传成功!'
    return '''
    <!doctype html>
    <title>上传新文件</title>
    <h1>上传新文件</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=上传>
    </form>
    '''

if __name__ == '__main__':
    app.run(debug=True)