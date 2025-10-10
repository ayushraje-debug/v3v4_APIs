# 📁 Automation Scripts – Day 2 Operations

This repository provides automation scripts for performing **CRUD operations** and various **day-2 use cases** on different entities using **Prism v3** and **v4 APIs**. These scripts aim to simplify common admin tasks across virtual infrastructure.

> 🔧 Feel free to use, modify, or contribute to this repository!

---

## ✅ Prerequisites

Before running the scripts, ensure the following requirements are met:

1. 🔐 **Jumphost Access**: All scripts should be executed from a jumphost that has access to the target **Prism cluster environment**.
2. 🐍 **Python 3.12**: Ensure Python version 3.12 is installed on the jumphost.
3. 🔑 **Valid Credentials**: Use an account with API access permissions.  
   - For v4 APIs, **Service Accounts** are supported and recommended where applicable.

---

## 📦 Setup & Usage

> _Typically, you'll want to create a virtual environment and install required packages listed in a `requirements.txt` file._
1. Create a python virtual-environment in a desired folder:
   - <pre> python -m venv venv </pre>

2. Activate the environment:
   > For Linux:
     - <pre> source venv\bin\activate </pre>
   > For Windows:
     - <pre> venv\Scripts\activate </pre>
     
3. Copy and Install dependencies:
   - Copy the `requirements.txt` to your folder and run
   - <pre> pip install -r requirements.txt </pre>
   
4. Copy the file matching the use case to your folder and execute the commands depending on that script.

---

## 📘 Available Scripts

### 🔹 V3 API Scripts

1. **Filter VMs by Name**  
   Retrieve virtual machines that match a given name or pattern.

2. **Add VMs to Categories**  
   Associate VMs with one or more categories using their names.

3. **Remove VMs from Categories**  
   Detach VMs from specified categories based on VM names.

4. **Fetch & Delete Orphan Recovery Points**  
   Identify and delete unused recovery points for:  
   - Deleted VMs  
   - Migrated VMs  
   - Existing but unprotected VMs

---

### 🔸 V4 API Scripts

1. **Get VM & Host Inventory Metrics**  
   Fetch detailed inventory metrics using v4 API, including VM and host utilization data.

---

## 🤝 Contributing

Contributions are welcome! Feel free to fork the repo and submit pull requests for new scripts, improvements, or bug fixes.

---

## 📬 Support

For issues or feature requests, please open a GitHub issue or reach out to the maintainers.
