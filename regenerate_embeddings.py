import os
import glob
from pathlib import Path
from app import create_app
from backend.database.db import db
from backend.models.student import Student
from backend.services.embedding_service import EmbeddingService

def migrate_embeddings_to_fast_model():
    app = create_app()
    with app.app_context():
        print("Initializing new fast model (buffalo_s)...")
        app.config["INSIGHTFACE_MODEL"] = "buffalo_s"
        app.config["RECOGNITION_THRESHOLD"] = 0.50
        
        # Initialize the embedding service with the fast model
        svc = EmbeddingService(model_name="buffalo_s")
        
        students = Student.query.all()
        print(f"Found {len(students)} students in the database.")
        
        images_dir = Path(app.config["FACE_IMAGES_FOLDER"])
        success_count = 0
        
        for student in students:
            student_id = student.student_id
            
            # Find all images for this student across all session folders
            search_pattern = str(images_dir / "**" / f"{student_id}_face_*.jpg")
            image_paths = glob.glob(search_pattern, recursive=True)
            
            if not image_paths:
                print(f"Warning: No original images found for student {student_id}. Cannot update.")
                continue
                
            print(f"Regenerating embedding for {student_id} using {len(image_paths)} original images...")
            
            embedding, error = svc.generate_from_images(image_paths)
            if error:
                print(f"Failed to generate embedding for {student_id}: {error}")
                continue
                
            student.set_embedding(embedding)
            db.session.commit()
            success_count += 1
            print(f"Successfully updated embedding for {student_id}")
            
        print(f"\nMigration complete! {success_count}/{len(students)} students successfully updated to buffalo_s.")

if __name__ == "__main__":
    migrate_embeddings_to_fast_model()
