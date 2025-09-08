"""
Service layer for Opportunity-related business logic.
Centralizes opportunity management to avoid code duplication.
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class OpportunityService:
    """Service class for managing Opportunity operations."""
    
    @staticmethod
    def add_sample_ids(opportunity, sample_ids: List[str], mark_for_update: bool = True) -> None:
        """
        Add sample IDs to an opportunity's sample_ids field.
        
        Args:
            opportunity: The Opportunity model instance
            sample_ids: List of sample IDs to add
            mark_for_update: Whether to set the update flag
        """
        # Get existing sample IDs and strip whitespace
        existing_ids = [id.strip() for id in opportunity.sample_ids.split(',') if id.strip()] if opportunity.sample_ids else []
        
        # Add new IDs, avoiding duplicates
        for sample_id in sample_ids:
            str_id = str(sample_id).strip()
            if str_id and str_id not in existing_ids:
                existing_ids.append(str_id)
        
        # Update the opportunity
        opportunity.sample_ids = ','.join(existing_ids) if existing_ids else ''
        if mark_for_update:
            opportunity.update = True
        opportunity.save()
        
        logger.debug(f"Added {len(sample_ids)} sample IDs to opportunity {opportunity.opportunity_number}")
    
    @staticmethod
    def remove_sample_id(opportunity, sample_id: str, mark_for_update: bool = True) -> None:
        """
        Remove a sample ID from an opportunity's sample_ids field.
        
        Args:
            opportunity: The Opportunity model instance
            sample_id: The sample ID to remove
            mark_for_update: Whether to set the update flag
        """
        # Get existing sample IDs and strip whitespace
        sample_ids = [id.strip() for id in opportunity.sample_ids.split(',') if id.strip()] if opportunity.sample_ids else []
        
        # Remove the specified ID
        str_id = str(sample_id).strip()
        if str_id in sample_ids:
            sample_ids.remove(str_id)
            
        # Update the opportunity - ensure empty string when no IDs remain
        if sample_ids:
            opportunity.sample_ids = ','.join(sample_ids)
        else:
            opportunity.sample_ids = ''
            
        if mark_for_update:
            opportunity.update = True
        opportunity.save()
        
        logger.debug(f"Removed sample ID {sample_id} from opportunity {opportunity.opportunity_number}")
    
    @staticmethod
    def update_opportunity_fields(opportunity, customer: Optional[str] = None, 
                                 rsm: Optional[str] = None, 
                                 description: Optional[str] = None,
                                 date_received: Optional = None) -> bool:
        """
        Update opportunity fields if new data is provided.
        
        Args:
            opportunity: The Opportunity model instance
            customer: New customer name (optional)
            rsm: New RSM name (optional)
            description: New description (optional)
            date_received: New date received (optional)
            
        Returns:
            bool: True if any fields were updated, False otherwise
        """
        updated = False
        
        if customer and customer != opportunity.customer:
            opportunity.customer = customer
            updated = True
            
        if rsm and rsm != opportunity.rsm:
            opportunity.rsm = rsm
            updated = True
            
        if description and description != opportunity.description:
            opportunity.description = description
            updated = True
            
        if date_received and date_received != opportunity.date_received:
            opportunity.date_received = date_received
            updated = True
        
        if updated:
            opportunity.update = True
            opportunity.save()
            logger.debug(f"Opportunity {opportunity.opportunity_number} updated with new data")
        
        return updated
    
    @staticmethod
    def sync_sample_ids(opportunity) -> None:
        """
        Synchronize the opportunity's sample_ids field with actual samples in database.
        
        Args:
            opportunity: The Opportunity model instance
        """
        from samples.models import Sample
        
        # Get all samples for this opportunity
        sample_ids = list(Sample.objects.filter(
            opportunity_number=opportunity.opportunity_number
        ).values_list('unique_id', flat=True))
        
        # Update the opportunity
        opportunity.sample_ids = ','.join(str(sid) for sid in sample_ids)
        opportunity.update = True
        opportunity.save()
        
        logger.info(f"Synchronized {len(sample_ids)} sample IDs for opportunity {opportunity.opportunity_number}")
    
    @staticmethod
    def should_archive(opportunity) -> bool:
        """
        Check if an opportunity should be archived (no samples remaining).
        
        Args:
            opportunity: The Opportunity model instance
            
        Returns:
            bool: True if opportunity should be archived
        """
        # Strip whitespace and filter out empty strings
        sample_ids = [id.strip() for id in opportunity.sample_ids.split(',') if id.strip()] if opportunity.sample_ids else []
        
        # Also verify against actual database records as a safety check
        from samples.models import Sample
        actual_sample_count = Sample.objects.filter(opportunity_number=opportunity.opportunity_number).count()
        
        # Archive if no sample IDs in the field AND no actual samples in database
        return len(sample_ids) == 0 and actual_sample_count == 0