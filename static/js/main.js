// Function to handle direct file downloads without password prompt
function downloadFile(fileId) {
    window.location.href = `/download/${fileId}`;
    return false;
}

// Handle password confirmation
function validatePasswords(formId) {
    const form = document.getElementById(formId);
    const password = form.querySelector('input[name="password"]');
    const confirmPassword = form.querySelector('input[name="confirm_password"]');
    
    if (password && confirmPassword) {
        if (password.value !== confirmPassword.value) {
            alert('Passwords do not match!');
            return false;
        }
    }
    return true;
}

// Initialize all forms and UI elements
document.addEventListener('DOMContentLoaded', function() {
    // Handle file upload form
    const uploadForm = document.getElementById('upload-form');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            const fileInput = document.getElementById('file-input');
            const passwordInput = document.getElementById('file-password');
            
            if (!fileInput.files.length) {
                e.preventDefault();
                alert('Please select a file to upload');
                return false;
            }
            
            if (!passwordInput.value) {
                e.preventDefault();
                alert('Please enter a password for the file. This will be required to extract the ZIP file.');
                return false;
            }
        });
    }

    // Handle admin form submission
    const adminForm = document.querySelector('form[action*="add_admin"]');
    if (adminForm) {
        adminForm.addEventListener('submit', function(e) {
            e.preventDefault();
            if (validatePasswords('admin-form')) {
                this.submit();
            }
        });
    }

    // Handle signup form submission
    const signupForm = document.querySelector('form[action*="signup"]');
    if (signupForm) {
        signupForm.addEventListener('submit', function(e) {
            e.preventDefault();
            if (validatePasswords('signup-form')) {
                this.submit();
            }
        });
    }

    // Add hover effects to file cards
    const fileCards = document.querySelectorAll('.file-card');
    fileCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px)';
            this.style.boxShadow = '0 4px 15px rgba(0,0,0,0.1)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '0 2px 4px rgba(0,0,0,0.1)';
        });
    });
});
