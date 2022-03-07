# first stage
FROM python:3.10
COPY requirements.txt .

# install dependencies to the local user directory (eg. /root/.local)
RUN pip install --user -r requirements.txt

WORKDIR /code

COPY ./ .

# update PATH
ENV PATH=/root/.local:$PATH

# make sure you include the -u flag to have our stdout logged
# CMD [ "python", "-u", "./main.py" ]