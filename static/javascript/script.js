document.addEventListener('DOMContentLoaded', function() {
    console.log('Enhanced video server is ready!');
    
    // Elements
    const videoModal = document.getElementById('video-modal');
    const modalVideo = document.getElementById('modal-video');
    const modalTitle = document.getElementById('modal-title');
    const closeModal = document.querySelector('.close-modal');
    const deleteModal = document.getElementById('delete-confirmation');
    const confirmDelete = document.getElementById('confirm-delete');
    const cancelDelete = document.getElementById('cancel-delete');
    
    let currentVideoToDelete = null;
    
    // Play button functionality
    const playButtons = document.querySelectorAll('.play-btn');
    playButtons.forEach(button => {
        button.addEventListener('click', function() {
            const videoName = this.getAttribute('data-video');
            const videoSrc = `/video/${videoName}`;
            
            // Set up the modal
            modalTitle.textContent = videoName;
            modalVideo.querySelector('source').src = videoSrc;
            modalVideo.load(); // Important: reload the video with the new source
            
            // Show the modal
            videoModal.style.display = 'block';
            
            // Play video
            modalVideo.play();
        });
    });
    
    // Delete button functionality
    const deleteButtons = document.querySelectorAll('.delete-btn');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function() {
            const videoName = this.getAttribute('data-video');
            currentVideoToDelete = videoName;
            
            // Show the delete confirmation modal
            deleteModal.style.display = 'block';
        });
    });
    
    // Confirm delete action
    confirmDelete.addEventListener('click', function() {
        if (currentVideoToDelete) {
            window.location.href = `/delete/${currentVideoToDelete}`;
        }
    });
    
    // Cancel delete action
    cancelDelete.addEventListener('click', function() {
        deleteModal.style.display = 'none';
        currentVideoToDelete = null;
    });
    
    // Close modal when clicking the X
    closeModal.addEventListener('click', function() {
        videoModal.style.display = 'none';
        modalVideo.pause();
    });
    
    // Close modals when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target === videoModal) {
            videoModal.style.display = 'none';
            modalVideo.pause();
        }
        
        if (event.target === deleteModal) {
            deleteModal.style.display = 'none';
            currentVideoToDelete = null;
        }
    });
    
    // Close modal with escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            if (videoModal.style.display === 'block') {
                videoModal.style.display = 'none';
                modalVideo.pause();
            }
            
            if (deleteModal.style.display === 'block') {
                deleteModal.style.display = 'none';
                currentVideoToDelete = null;
            }
        }
    });
});
